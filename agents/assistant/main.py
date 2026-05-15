# SPDX-License-Identifier: Apache-2.0

import asyncio
import hashlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
import yaml
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import InMemoryQueueManager
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore, InMemoryTaskStore
from a2a.types import AgentCapabilities
from google.adk.agents import LlmAgent
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)
from starlette.applications import Starlette

from callbacks import after_agent, before_agent
from event_converter import convert_event_with_yaml_metadata

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("MODEL_NAME", "claude-opus-4-6")
PORT = int(os.environ.get("PORT", "8080"))

GEMARA_MCP_URL = os.environ.get("GEMARA_MCP_URL", "")
STUDIO_MCP_URL = os.environ.get("STUDIO_MCP_URL", "")


def load_skills() -> str:
    skills_dir = Path("/app/skills")
    if not skills_dir.exists():
        return ""
    parts = []
    for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
        parts.append(skill_file.read_text())
    return "\n\n---\n\n".join(parts)


def load_few_shot_examples() -> str:
    """Read YAML few-shot files and format into a prompt section."""
    few_shot_dir = Path("/app/prompts/few-shot")
    if not few_shot_dir.exists():
        return ""
    parts: list[str] = []
    for f in sorted(few_shot_dir.glob("*.yaml")):
        try:
            examples = yaml.safe_load(f.read_text())
        except yaml.YAMLError:
            logger.warning("Skipping malformed few-shot file: %s", f.name)
            continue
        if not isinstance(examples, list):
            continue
        for ex in examples:
            if not isinstance(ex, dict) or "scenario" not in ex:
                continue
            lines = [f"**Scenario:** {ex['scenario']}"]
            if ex.get("evidence"):
                lines.append(f"**Evidence:** {ex['evidence']}")
            elif ex.get("audit_result_type"):
                lines.append(f"**AuditResult type:** {ex['audit_result_type']}")
                if ex.get("mapping"):
                    lines.append(f"**Mapping:** {ex['mapping']}")
            for key in ("classification", "determination", "coverage"):
                if key in ex:
                    lines.append(f"**{key.title()}:** {ex[key]}")
            if ex.get("reasoning"):
                lines.append(f"**Reasoning:** {ex['reasoning'].strip()}")
            parts.append("\n".join(lines))
    if not parts:
        return ""
    return "## Classification Examples\n\n" + "\n\n---\n\n".join(parts)


def load_prompt() -> str:
    prompt_path = Path("/app/prompt.md")
    base_prompt = prompt_path.read_text()
    skills_text = load_skills()
    if skills_text:
        base_prompt = f"{base_prompt}\n\n## Loaded Skills\n\n{skills_text}"
    few_shot_text = load_few_shot_examples()
    if few_shot_text:
        base_prompt = f"{base_prompt}\n\n{few_shot_text}"
    return base_prompt


LEXICON_RESOURCE = "gemara-lexicon"


async def _fetch_gemara_lexicon(url: str) -> str:
    """Preload only the Gemara lexicon for prompt injection.

    The full schema/definitions (~44K chars) is deliberately excluded —
    it causes attention dilution and field-name confusion in the LLM.
    """
    ts = McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=url),
        use_mcp_resources=True,
    )
    try:
        contents = await ts.read_resource(LEXICON_RESOURCE)
        for item in contents:
            text = item.text if hasattr(item, "text") else str(item)
            logger.info("preloaded resource %s (%d chars)", LEXICON_RESOURCE, len(text))
            return f"## Gemara Lexicon\n\n```\n{text}\n```"
    except Exception as e:
        logger.warning("failed to read lexicon: %s", e)
    finally:
        await ts.close()
    return ""


def _probe_mcp_sync(url: str, label: str, retries: int = 15, delay: float = 4.0) -> bool:
    """Block until an MCP server responds. Runs at startup before the event loop."""
    import time
    import httpx

    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(
                url,
                json={"jsonrpc": "2.0", "method": "initialize", "id": 0, "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "probe", "version": "0.0.1"},
                }},
                headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                timeout=5.0,
            )
            if resp.status_code < 500:
                logger.info("%s reachable (attempt %d/%d, status=%d)", label, attempt, retries, resp.status_code)
                return True
        except Exception as e:
            logger.warning("%s unreachable (attempt %d/%d): %s", label, attempt, retries, e)
        time.sleep(delay)
    logger.error("%s not reachable after %d attempts — skipping toolset registration", label, retries)
    return False


def build_tools() -> list:
    tools = []

    if GEMARA_MCP_URL:
        if _probe_mcp_sync(GEMARA_MCP_URL, "gemara-mcp"):
            tools.append(
                McpToolset(
                    connection_params=StreamableHTTPConnectionParams(url=GEMARA_MCP_URL),
                    tool_filter=["validate_gemara_artifact", "migrate_gemara_artifact"],
                )
            )
            logger.info("gemara-mcp toolset registered (url=%s)", GEMARA_MCP_URL)
        else:
            logger.error("gemara-mcp unreachable — tools will not be available")

    if STUDIO_MCP_URL:
        if _probe_mcp_sync(STUDIO_MCP_URL, "studio-mcp"):
            tools.append(
                McpToolset(
                    connection_params=StreamableHTTPConnectionParams(url=STUDIO_MCP_URL),
                    tool_filter=["query_evidence", "save_draft_audit_log"],
                    use_mcp_resources=True,
                )
            )
            logger.info("studio-mcp toolset registered (url=%s)", STUDIO_MCP_URL)
        else:
            logger.error(
                "studio-mcp unreachable — query_evidence/save_draft_audit_log "
                "and studio:// resources will not be available"
            )

    if not tools:
        logger.warning("No MCP servers reachable — agent running without tools")

    return tools


def _build_instruction() -> str:
    base = load_prompt()
    if GEMARA_MCP_URL:
        try:
            lexicon_text = asyncio.run(_fetch_gemara_lexicon(GEMARA_MCP_URL))
            if lexicon_text:
                base = f"{base}\n\n{lexicon_text}"
        except Exception as e:
            logger.warning("resource preload failed: %s", e)
    return base


_INSTRUCTION = _build_instruction()
PROMPT_VERSION = hashlib.sha256(_INSTRUCTION.encode()).hexdigest()[:12]
logger.info("prompt_version=%s model=%s", PROMPT_VERSION, MODEL_NAME)

root_agent = LlmAgent(
    name="studio_assistant",
    model=MODEL_NAME,
    instruction=_INSTRUCTION,
    tools=build_tools(),
    description=(
        "ComplyTime Studio assistant — audit preparation, evidence synthesis, "
        "cross-framework coverage analysis, and compliance guidance"
    ),
    before_agent_callback=before_agent,
    after_agent_callback=after_agent,
)


# --- Manual A2aAgentExecutor setup (replaces to_a2a()) ---
# Shared services must be singletons so multi-turn conversations
# within the same task retain session and memory state.

_session_service = InMemorySessionService()
_artifact_service = InMemoryArtifactService()
_memory_service = InMemoryMemoryService()
_credential_service = InMemoryCredentialService()


async def create_runner() -> Runner:
    return Runner(
        app_name="studio_assistant",
        agent=root_agent,
        artifact_service=_artifact_service,
        session_service=_session_service,
        memory_service=_memory_service,
        credential_service=_credential_service,
    )


config = A2aAgentExecutorConfig(
    adk_event_converter=convert_event_with_yaml_metadata,
)

agent_executor = A2aAgentExecutor(
    runner=create_runner,
    config=config,
)

task_store = InMemoryTaskStore()
push_config_store = InMemoryPushNotificationConfigStore()
queue_manager = InMemoryQueueManager()

request_handler = DefaultRequestHandler(
    agent_executor=agent_executor,
    task_store=task_store,
    push_config_store=push_config_store,
    queue_manager=queue_manager,
)

rpc_url = f"http://0.0.0.0:{PORT}/"
card_builder = AgentCardBuilder(
    agent=root_agent,
    rpc_url=rpc_url,
    capabilities=AgentCapabilities(streaming=True),
)


@asynccontextmanager
async def lifespan(app: Starlette):
    agent_card = await card_builder.build()
    a2a_app = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    a2a_app.add_routes_to_app(app)
    logger.info("A2A routes registered, agent card built for %s", root_agent.name)
    yield


app = Starlette(lifespan=lifespan)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
