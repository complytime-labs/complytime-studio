# SPDX-License-Identifier: Apache-2.0

"""Deterministic intent router for the Studio assistant.

Classifies user intent via keyword matching first, LLM fallback second.
Replaces prompt-based routing with graph-enforced workflow selection.
"""

import logging

logger = logging.getLogger(__name__)

POSTURE_KEYWORDS: list[str] = [
    "posture",
    "readiness",
    "status",
    "how ready",
    "assessment plan",
    "evidence quality",
    "are we compliant",
    "health check",
    "pre-audit",
]

AUDIT_KEYWORDS: list[str] = [
    "run an audit",
    "run audit",
    "produce an auditlog",
    "produce auditlog",
    "generate audit",
    "audit results",
    "audit log",
    "auditlog",
    "full audit",
    "start audit",
]


def classify_intent(message: str) -> str:
    """Classify user intent from message text.

    Returns "posture_check", "audit_production", or "" (ambiguous).
    Uses case-insensitive substring matching against keyword lists.
    """
    text = message.lower().strip()

    for keyword in AUDIT_KEYWORDS:
        if keyword in text:
            return "audit_production"

    for keyword in POSTURE_KEYWORDS:
        if keyword in text:
            return "posture_check"

    return ""


def router_node(state: dict) -> dict:
    """Graph node: classify intent and set state.

    If intent is already set (non-empty), this is a no-op — the router
    fires only once per conversation.
    """
    if state.get("intent"):
        return {}

    messages = state.get("messages", [])
    if not messages:
        return {}

    last_msg = messages[-1]
    text = ""
    if hasattr(last_msg, "content"):
        text = last_msg.content if isinstance(last_msg.content, str) else ""

    intent = classify_intent(text)
    if intent:
        logger.info("Router classified intent: %s (keyword match)", intent)
        return {"intent": intent}

    logger.info("Router: no keyword match, returning ambiguous")
    return {"intent": ""}


def route_by_intent(state: dict) -> str:
    """Conditional edge function: route based on classified intent."""
    intent = state.get("intent", "")
    if intent == "posture_check":
        return "posture_check"
    if intent == "audit_production":
        return "audit_production"
    return "clarify"
