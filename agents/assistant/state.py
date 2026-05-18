# SPDX-License-Identifier: Apache-2.0

"""LangGraph state schema for the Studio assistant.

Extends beyond flat messages to include structured working memory
that survives message window truncation. All fields are checkpointed
by PostgresSaver.
"""

from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AuditState(TypedDict):
    """Full state schema for the assistant graph.

    Fields beyond `messages` persist structured working memory across
    the message window boundary and through interrupt/resume cycles.
    """

    messages: Annotated[Sequence[BaseMessage], add_messages]

    intent: str
    """Classified user intent: "posture_check", "audit_production", or ""."""

    draft_yaml: str
    """Current draft artifact YAML content awaiting validation."""

    evidence_refs: list[str]
    """Evidence IDs referenced in the current draft."""

    validation_result: dict
    """Latest validation outcome: {"valid": bool, "errors": [...]}."""

    validation_attempts: int
    """Counter for retry budget enforcement (max 3)."""

    target_inventory: list[dict]
    """Discovered targets: [{"target_id": str, "target_name": str}]."""

    needs_delegation: bool
    """Flag set when BYO worker data is required."""

    delegation_target: str
    """Agent ID to delegate to (resolved from agentDirectory)."""

    worker_data: dict
    """Responses from BYO agents, keyed by agent ID."""
