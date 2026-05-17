# SPDX-License-Identifier: Apache-2.0

"""Graph nodes for the Studio assistant that are not LLM invocations.

These are deterministic functions called as LangGraph nodes:
- extract_draft_node: parses draft YAML from LLM output into state
- publish_draft_node: persists validated AuditLog via gateway REST API
- halt_node: terminal node emitting accumulated errors
- clarify_node: asks user to disambiguate intent
"""

import logging
import re

from langchain_core.messages import AIMessage

from tools import publish_audit_log

logger = logging.getLogger(__name__)

_YAML_FENCE_RE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)


def extract_draft_node(state: dict) -> dict:
    """Graph node: extract draft YAML and evidence refs from the last message.

    Runs between the agent loop exit and validate_draft. Parses fenced
    YAML blocks from the LLM's response and populates draft_yaml and
    evidence_refs in state so the validation harness has data to check.
    """
    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    content = ""
    if hasattr(last_msg, "content"):
        content = last_msg.content if isinstance(last_msg.content, str) else ""

    if not content:
        return {}

    match = _YAML_FENCE_RE.search(content)
    if match:
        draft = match.group(1).strip()
    elif content.strip().startswith("metadata:"):
        draft = content.strip()
    else:
        return {}

    evidence_refs = _extract_evidence_refs(draft)
    logger.info(
        "Extracted draft (%d chars, %d evidence refs)",
        len(draft),
        len(evidence_refs),
    )
    return {"draft_yaml": draft, "evidence_refs": evidence_refs}


def _extract_evidence_refs(yaml_content: str) -> list[str]:
    """Extract evidence reference IDs from draft YAML."""
    refs = []
    for match in re.finditer(r"reference-id:\s*(\S+)", yaml_content):
        ref = match.group(1)
        if ref not in refs:
            refs.append(ref)
    return refs


async def publish_draft_node(state: dict) -> dict:
    """Graph node: publish the validated draft AuditLog via gateway REST API.

    Reached only after validation gate passes AND human approves
    at the interrupt gate. Calls publish_audit_log (gateway @tool)
    and emits a confirmation message.
    """
    draft = state.get("draft_yaml", "")
    if not draft:
        msg = AIMessage(
            content="Error: no draft to publish. Validation gate should have caught this."
        )
        return {"messages": [msg]}

    policy_id = ""
    match = re.search(r"policy[_-]id:\s*(\S+)", draft)
    if match:
        policy_id = match.group(1)

    reasoning = state.get("_reasoning", "")
    result = await publish_audit_log(draft, policy_id=policy_id, reasoning=reasoning)

    if "error" in result:
        msg = AIMessage(content=f"Failed to publish draft: {result['error']}")
    else:
        draft_id = result.get("draft_id", "unknown")
        msg = AIMessage(
            content=(
                f"Draft AuditLog saved for review (draft_id: {draft_id}). "
                "A reviewer must promote it to the official audit history."
            )
        )

    return {"messages": [msg]}


async def halt_node(state: dict) -> dict:
    """Graph node: terminal halt after retry exhaustion or infra failure.

    Emits all accumulated validation errors to the user.
    """
    result = state.get("validation_result", {})
    errors = result.get("errors", ["Unknown validation failure"])
    attempts = state.get("validation_attempts", 0)

    error_list = "\n".join(f"- {e}" for e in errors)
    msg = AIMessage(
        content=(
            f"Validation failed after {attempts} attempts. "
            "Human intervention required.\n\n"
            f"**Errors:**\n{error_list}"
        )
    )
    return {"messages": [msg]}


async def clarify_node(state: dict) -> dict:
    """Graph node: ask user to disambiguate intent."""
    msg = AIMessage(
        content=(
            "Do you want a **posture check** (readiness overview — "
            "is your evidence current and from the right sources?) "
            "or a **full audit** (AuditLog production with classifications)?"
        )
    )
    return {"messages": [msg]}
