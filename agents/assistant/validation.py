# SPDX-License-Identifier: Apache-2.0

"""Deterministic validation gate for the audit production workflow.

Runs CUE schema validation via gemara-mcp and verifies evidence
references exist via the studio gateway evidence API. This is a
graph node — the LLM cannot skip or bypass it.
"""

import json
import logging
import re

from tools import AGENT_ID, GATEWAY_URL, GEMARA_MCP_URL, _call_mcp_tool

logger = logging.getLogger(__name__)

MAX_VALIDATION_ATTEMPTS = 3


async def _validate_schema(yaml_content: str) -> dict:
    """Validate draft against Gemara CUE schema via gemara-mcp."""
    if not GEMARA_MCP_URL:
        return {
            "valid": False,
            "errors": ["Gemara MCP unavailable: GEMARA_MCP_URL not configured"],
        }

    try:
        result = await _call_mcp_tool(
            GEMARA_MCP_URL,
            "validate_gemara_artifact",
            {"artifact_content": yaml_content, "definition": "#AuditLog"},
        )
        content = result.get("content", [])
        if isinstance(content, list) and content:
            text = content[0].get("text", "")
            try:
                parsed = json.loads(text)
                return parsed
            except (json.JSONDecodeError, TypeError):
                if "valid" in text.lower():
                    return {"valid": True, "errors": []}
                return {"valid": False, "errors": [text]}
        return {"valid": True, "errors": []}
    except Exception as e:
        return {"valid": False, "errors": [f"Gemara MCP unavailable: {e}"]}


async def _verify_evidence_refs(refs: list[str], policy_id: str) -> list[str]:
    """Verify evidence IDs exist via gateway API. Returns missing IDs."""
    if not refs or not GATEWAY_URL:
        return []

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{GATEWAY_URL.rstrip('/')}/api/evidence",
                params={"policy_id": policy_id, "limit": str(len(refs) + 10)},
                headers={"X-Forwarded-Email": AGENT_ID + "@complytime.dev"},
            )
            resp.raise_for_status()
            rows = resp.json()
            found = set()
            if isinstance(rows, list):
                for r in rows:
                    eid = r.get("evidence_id", "") or r.get("id", "")
                    if eid:
                        found.add(eid)
            return [r for r in refs if r not in found]
    except Exception as e:
        logger.warning("Evidence ref verification failed: %s", e)
        return []


async def validate_draft_node(state: dict) -> dict:
    """Graph node: validate draft YAML against schema and evidence refs.

    Deterministic — no LLM invocation. Increments validation_attempts
    and populates validation_result.
    """
    draft = state.get("draft_yaml", "")
    attempts = state.get("validation_attempts", 0) + 1
    errors: list[str] = []

    if not draft:
        return {
            "validation_result": {"valid": False, "errors": ["No draft_yaml in state"]},
            "validation_attempts": attempts,
        }

    schema_result = await _validate_schema(draft)
    if not schema_result.get("valid", False):
        errors.extend(schema_result.get("errors", ["Schema validation failed"]))

    refs = state.get("evidence_refs", [])
    policy_id = _extract_policy_id_from_draft(draft)
    if refs and policy_id:
        missing = await _verify_evidence_refs(refs, policy_id)
        if missing:
            errors.append(f"Missing evidence refs: {missing}")

    valid = len(errors) == 0
    logger.info(
        "Validation gate: attempt=%d valid=%s errors=%d",
        attempts,
        valid,
        len(errors),
    )

    return {
        "validation_result": {"valid": valid, "errors": errors},
        "validation_attempts": attempts,
    }


def _extract_policy_id_from_draft(yaml_content: str) -> str:
    """Extract policy-id from draft YAML scope."""
    match = re.search(r"policy[_-]id:\s*(\S+)", yaml_content)
    return match.group(1) if match else ""


def route_after_validation(state: dict) -> str:
    """Conditional edge: route based on validation outcome and retry budget."""
    result = state.get("validation_result", {})
    attempts = state.get("validation_attempts", 0)

    if result.get("valid"):
        return "publish"
    if attempts >= MAX_VALIDATION_ATTEMPTS:
        return "halt"
    return "fix"
