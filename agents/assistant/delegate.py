# SPDX-License-Identifier: Apache-2.0

"""A2A delegation node for the Studio assistant.

Makes A2A calls to registered BYO agents and writes responses into
state.worker_data. This is a graph node — delegation fires
deterministically based on the needs_delegation state flag.
"""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

WORKBENCH_URL = os.environ.get("WORKBENCH_URL", "http://studio-workbench:8090")
AGENT_ID = os.environ.get("AGENT_ID", "studio-assistant")

_TIMEOUT = 30.0
_MAX_RESPONSE_BYTES = 1_048_576  # 1MB


async def _resolve_agent_url(agent_id: str) -> str | None:
    """Resolve a BYO agent's A2A URL from the workbench agent directory."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{WORKBENCH_URL}/workbench/agents")
            if resp.status_code != 200:
                return None
            agents = resp.json()
            for agent in agents:
                if agent.get("name") == agent_id:
                    return agent.get("url", "")
    except Exception as e:
        logger.error("Failed to resolve agent %s: %s", agent_id, e)
    return None


async def _call_a2a(url: str, message: str, context: str = "") -> dict:
    """Send an A2A message/send request to a BYO agent."""
    parts = [{"kind": "text", "text": message}]
    if context:
        parts.append(
            {"kind": "text", "text": f"--- Context (reference only) ---\n{context}"}
        )

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {"message": {"role": "user", "parts": parts}},
    }

    headers = {
        "Content-Type": "application/json",
        "X-Agent-ID": AGENT_ID,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()

            if len(resp.content) > _MAX_RESPONSE_BYTES:
                text = resp.text[:_MAX_RESPONSE_BYTES]
                return {
                    "data": text + "\n[TRUNCATED — response exceeded 1MB]",
                    "truncated": True,
                }

            result = resp.json()

            if "error" in result:
                return {
                    "error": f"A2A error: {result['error'].get('message', str(result['error']))}"
                }

            task = result.get("result", {})
            status = task.get("status", {})
            if status.get("state") == "failed":
                fail_msg = (
                    status.get("message", {})
                    .get("parts", [{}])[0]
                    .get("text", "unknown failure")
                )
                return {"error": f"Agent reported failure: {fail_msg}"}

            artifacts = task.get("artifacts", [])
            response_parts = []
            for artifact in artifacts:
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        response_parts.append(part.get("text", ""))

            if not response_parts and status.get("message"):
                msg_parts = status["message"].get("parts", [])
                for part in msg_parts:
                    if isinstance(part, dict) and part.get("kind") == "text":
                        response_parts.append(part.get("text", ""))

            return {
                "data": "\n".join(response_parts)
                if response_parts
                else "Empty response"
            }

    except httpx.TimeoutException:
        return {"error": f"Agent timed out after {_TIMEOUT}s"}
    except httpx.HTTPStatusError as e:
        return {"error": f"Agent returned HTTP {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Delegation failed: {e}"}


async def delegate_node(state: dict) -> dict:
    """Graph node: delegate to a BYO agent via A2A.

    Resolves the target agent from the directory, sends a structured
    request, and writes the response into state.worker_data.
    """
    target = state.get("delegation_target", "")
    if not target:
        logger.warning("delegate_node called without delegation_target set")
        return {
            "worker_data": {"error": "No delegation_target specified"},
            "needs_delegation": False,
        }

    url = await _resolve_agent_url(target)
    if not url:
        error = f"Agent '{target}' not found in directory"
        logger.error(error)
        return {
            "worker_data": {target: {"error": error}},
            "needs_delegation": False,
        }

    messages = state.get("messages", [])
    draft = state.get("draft_yaml", "")
    policy_id = ""
    if draft:
        match = re.search(r"policy[_-]id:\s*(\S+)", draft)
        if match:
            policy_id = match.group(1)

    context_parts = []
    if policy_id:
        context_parts.append(f"policy_id: {policy_id}")
    targets = state.get("target_inventory", [])
    if targets:
        context_parts.append(f"targets: {json.dumps(targets)}")

    last_user_msg = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            last_user_msg = msg.content if isinstance(msg.content, str) else ""
            break
        elif hasattr(msg, "role") and getattr(msg, "role", "") == "user":
            last_user_msg = msg.content if isinstance(msg.content, str) else ""
            break

    message = last_user_msg or f"Provide domain-specific data for policy {policy_id}"
    context = "\n".join(context_parts) if context_parts else ""

    logger.info("Delegating to %s at %s", target, url)
    result = await _call_a2a(url, message, context)

    current_worker_data = dict(state.get("worker_data", {}))
    current_worker_data[target] = result
    return {"worker_data": current_worker_data, "needs_delegation": False}
