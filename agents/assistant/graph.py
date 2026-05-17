# SPDX-License-Identifier: Apache-2.0

"""ComplyTime Studio assistant — LangGraph supervisor with verification harness.

Graph topology:
  __start__ -> router -> (posture_check | audit_production | clarify)

Audit production subgraph:
  agent -> tools -> agent ... -> extract_draft -> validate_draft -> (publish | fix | halt)
  publish has interrupt_before for human approval.

Posture check subgraph:
  agent -> tools -> agent ... -> __end__ (no publish path)
"""

import logging
import os

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from kagent.core import KAgentConfig
from kagent.langgraph import KAgentApp
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from delegate import delegate_node
from nodes import clarify_node, extract_draft_node, halt_node, publish_draft_node
from prompt import load_system_prompt
from router import route_by_intent, router_node
from state import AuditState
from tools import build_tools, sql_guard_filter
from validation import route_after_validation, validate_draft_node

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.environ.get("MODEL_NAME", "claude-opus-4-6")
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "AnthropicVertexAI")
PORT = int(os.environ.get("PORT", "8080"))

GEMARA_MCP_URL = os.environ.get("GEMARA_MCP_URL", "")
POSTGRES_URL = os.environ.get("POSTGRES_URL", "")
AGENT_ID = os.environ.get("AGENT_ID", "studio-assistant")
KAGENT_URL = os.environ.get("KAGENT_URL", "http://kagent-controller:8083")
APP_NAME = os.environ.get("APP_NAME", "studio_assistant")


def _create_model():
    """Instantiate the chat model based on MODEL_PROVIDER."""
    if MODEL_PROVIDER == "AnthropicVertexAI":
        from langchain_google_vertexai.model_garden import ChatAnthropicVertex

        return ChatAnthropicVertex(
            model_name=MODEL_NAME,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-east5"),
            max_tokens=16384,
        )

    if MODEL_PROVIDER == "GeminiVertexAI":
        from langchain_google_vertexai import ChatVertexAI

        return ChatVertexAI(
            model_name=MODEL_NAME,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-east5"),
        )

    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(model=MODEL_NAME, max_tokens=16384)


def _build_mcp_servers() -> dict:
    """Build MCP server config for langchain-mcp-adapters."""
    headers = {"X-Agent-ID": AGENT_ID}
    servers = {}
    if GEMARA_MCP_URL:
        servers["gemara-mcp"] = {
            "transport": "streamable_http",
            "url": GEMARA_MCP_URL,
            "headers": headers,
        }
    if not servers:
        logger.warning("No MCP servers configured — agent running without MCP tools")
    return servers


def _build_checkpointer():
    """Build a KAgentCheckpointer backed by the kagent-controller API."""
    import httpx
    from kagent.langgraph._checkpointer import KAgentCheckpointer

    client = httpx.AsyncClient(base_url=KAGENT_URL, timeout=30.0)
    return KAgentCheckpointer(client=client, app_name=AGENT_ID)


def _build_audit_subgraph(model, mcp_servers: dict, system_prompt: str) -> StateGraph:
    """Build the audit production subgraph with verification harness."""
    local_tools = build_tools()

    async def agent_node(state: AuditState, config):
        """LLM reasoning node — tool selection and draft generation."""
        import json as _json

        messages = state["messages"]
        system_messages = [{"role": "system", "content": system_prompt}]

        worker_data = state.get("worker_data", {})
        if worker_data:
            data_context = (
                f"\n\n--- Worker Data (reference only) ---\n"
                f"{_json.dumps(worker_data, indent=2)}"
            )
            system_messages[0]["content"] += data_context

        tools_for_model = list(local_tools)
        if mcp_servers:
            client = MultiServerMCPClient(mcp_servers)
            mcp_tools = await client.get_tools()
            tools_for_model = tools_for_model + mcp_tools

        bound_model = model.bind_tools(tools_for_model)
        response = await bound_model.ainvoke(system_messages + list(messages))
        return {"messages": [response]}

    async def tool_node_fn(state: AuditState, config):
        """Execute tool calls with SQL write guard."""
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls"):
            for tc in last_msg.tool_calls:
                blocked = sql_guard_filter(tc.get("name", ""), tc.get("args", {}))
                if blocked:
                    from langchain_core.messages import ToolMessage

                    return {
                        "messages": [
                            ToolMessage(
                                content=str(blocked),
                                tool_call_id=tc.get("id", ""),
                            )
                        ]
                    }

        tools_for_node = list(local_tools)
        if mcp_servers:
            client = MultiServerMCPClient(mcp_servers)
            mcp_tools = await client.get_tools()
            tools_for_node = tools_for_node + mcp_tools
        node = ToolNode(tools_for_node, handle_tool_errors=True)
        return await node.ainvoke(state, config)

    def should_use_tool(state: AuditState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return "end_loop"

    def should_delegate(state: AuditState):
        if state.get("needs_delegation"):
            return "delegate"
        return "agent"

    builder = StateGraph(AuditState)
    builder.add_node("delegate", delegate_node)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node_fn)
    builder.add_node("extract_draft", extract_draft_node)
    builder.add_node("validate_draft", validate_draft_node)
    builder.add_node("publish_draft", publish_draft_node)
    builder.add_node("halt", halt_node)

    builder.add_conditional_edges(
        "__start__",
        should_delegate,
        {"delegate": "delegate", "agent": "agent"},
    )
    builder.add_edge("delegate", "agent")
    builder.add_conditional_edges(
        "agent",
        should_use_tool,
        {"tools": "tools", "end_loop": "extract_draft"},
    )
    builder.add_edge("extract_draft", "validate_draft")
    builder.add_edge("tools", "agent")
    builder.add_conditional_edges(
        "validate_draft",
        route_after_validation,
        {"publish": "publish_draft", "fix": "agent", "halt": "halt"},
    )
    builder.add_edge("publish_draft", END)
    builder.add_edge("halt", END)

    return builder


def _build_posture_subgraph(
    model, mcp_servers: dict, system_prompt: str
) -> StateGraph:
    """Build the posture check subgraph — no publish path."""
    local_tools = build_tools()

    async def agent_node(state: AuditState, config):
        """LLM reasoning node for posture checks."""
        messages = state["messages"]
        system_messages = [{"role": "system", "content": system_prompt}]

        tools_for_model = list(local_tools)
        if mcp_servers:
            client = MultiServerMCPClient(mcp_servers)
            mcp_tools = await client.get_tools()
            tools_for_model = tools_for_model + mcp_tools

        bound_model = model.bind_tools(tools_for_model)
        response = await bound_model.ainvoke(system_messages + list(messages))
        return {"messages": [response]}

    async def tool_node_fn(state: AuditState, config):
        """Execute tool calls with SQL write guard."""
        last_msg = state["messages"][-1]
        if hasattr(last_msg, "tool_calls"):
            for tc in last_msg.tool_calls:
                blocked = sql_guard_filter(tc.get("name", ""), tc.get("args", {}))
                if blocked:
                    from langchain_core.messages import ToolMessage

                    return {
                        "messages": [
                            ToolMessage(
                                content=str(blocked),
                                tool_call_id=tc.get("id", ""),
                            )
                        ]
                    }

        tools_for_node = list(local_tools)
        if mcp_servers:
            client = MultiServerMCPClient(mcp_servers)
            mcp_tools = await client.get_tools()
            tools_for_node = tools_for_node + mcp_tools
        node = ToolNode(tools_for_node, handle_tool_errors=True)
        return await node.ainvoke(state, config)

    def should_use_tool(state: AuditState):
        last = state["messages"][-1]
        if hasattr(last, "tool_calls") and last.tool_calls:
            return "tools"
        return END

    builder = StateGraph(AuditState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node_fn)

    builder.add_edge("__start__", "agent")
    builder.add_conditional_edges(
        "agent", should_use_tool, {"tools": "tools", END: END}
    )
    builder.add_edge("tools", "agent")

    return builder


def build_graph() -> StateGraph:
    """Construct the top-level supervisor graph with router and subgraphs."""
    system_prompt = load_system_prompt()
    model = _create_model()
    mcp_servers = _build_mcp_servers()

    audit_subgraph = _build_audit_subgraph(model, mcp_servers, system_prompt).compile(
        interrupt_before=["publish_draft"],
    )
    posture_subgraph = _build_posture_subgraph(
        model, mcp_servers, system_prompt
    ).compile()

    builder = StateGraph(AuditState)
    builder.add_node("router", router_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("audit_production", audit_subgraph)
    builder.add_node("posture_check", posture_subgraph)

    builder.add_edge("__start__", "router")
    builder.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "audit_production": "audit_production",
            "posture_check": "posture_check",
            "clarify": "clarify",
        },
    )
    builder.add_edge("audit_production", END)
    builder.add_edge("posture_check", END)
    builder.add_edge("clarify", END)

    return builder


_checkpointer = _build_checkpointer()
_builder = build_graph()
_compiled_graph = _builder.compile(checkpointer=_checkpointer)

_agent_card = AgentCard(
    name="studio_assistant",
    description=(
        "ComplyTime Studio assistant — audit preparation, evidence synthesis, "
        "cross-framework coverage analysis, and compliance guidance"
    ),
    version="0.2.0",
    url=f"http://localhost:{os.getenv('PORT', '8080')}",
    capabilities=AgentCapabilities(streaming=True),
    default_input_modes=["text"],
    default_output_modes=["text"],
    skills=[
        AgentSkill(
            id="compliance-assistant",
            name="Studio Assistant",
            description=(
                "Audit preparation, evidence synthesis, cross-framework coverage "
                "analysis, policy guidance, and AuditLog generation."
            ),
            tags=["assistant", "audit", "compliance", "coverage", "evidence"],
        )
    ],
)

_config = KAgentConfig(
    url=KAGENT_URL,
    name=APP_NAME,
    namespace=os.getenv("KAGENT_NAMESPACE", "kagent"),
)

_app = KAgentApp(
    graph=_compiled_graph,
    agent_card=_agent_card,
    config=_config,
)

graph = _app.build()
