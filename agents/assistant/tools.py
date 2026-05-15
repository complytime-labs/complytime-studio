# SPDX-License-Identifier: Apache-2.0

"""MCP tool helpers and SQL guard for the ComplyTime Studio assistant.

_call_mcp_tool: shared JSON-RPC helper for calling MCP tools
                programmatically from deterministic graph nodes.

SQL guard logic is applied as a pre-invocation check on any tool that
accepts raw SQL arguments. Protects against write operations regardless
of which MCP server exposes the tool.
"""

import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

STUDIO_MCP_URL = os.environ.get("STUDIO_MCP_URL", "")
GEMARA_MCP_URL = os.environ.get("GEMARA_MCP_URL", "")
AGENT_ID = os.environ.get("AGENT_ID", "studio-assistant")

_SQL_WRITE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC)\b",
    re.IGNORECASE,
)

GUARDED_TOOLS = frozenset({
    "query_database",
    "query_evidence",
    "execute_sql",
    "run_query",
})


async def _call_mcp_tool(url: str, tool_name: str, arguments: dict) -> dict:
    """Call an MCP tool via Streamable HTTP (JSON-RPC).

    Shared helper used by deterministic graph nodes (validation, publish)
    to call MCP tools without going through the LLM.
    """
    headers = {
        "Content-Type": "application/json",
        "X-Agent-ID": AGENT_ID,
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()
        if "error" in result:
            return {
                "valid": False,
                "errors": [result["error"].get("message", str(result["error"]))],
            }
        return result.get("result", {})


async def publish_audit_log(
    yaml_content: str,
    policy_id: str = "",
    reasoning: str = "",
) -> dict:
    """Publish a validated AuditLog YAML as a draft via studio-mcp.

    Called by the publish_draft graph node AFTER the validation gate
    passes and human approval is received. Not directly callable by
    the LLM.
    """
    if not STUDIO_MCP_URL:
        return {"error": "STUDIO_MCP_URL not configured"}

    model_name = os.environ.get("MODEL_NAME", "unknown")
    arguments = {
        "policy_id": policy_id,
        "yaml": yaml_content,
        "agent_reasoning": reasoning,
        "model": model_name,
        "prompt_version": "langgraph-v1",
    }

    try:
        result = await _call_mcp_tool(
            STUDIO_MCP_URL, "save_draft_audit_log", arguments
        )
        content = result.get("content", [])
        if isinstance(content, list) and content:
            text = content[0].get("text", "")
            try:
                parsed = json.loads(text)
                draft_id = parsed.get("draft_id", "")
                logger.info(
                    "persisted draft audit log %s (policy=%s)", draft_id, policy_id
                )
                return {
                    "status": "drafted",
                    "draft_id": draft_id,
                    "note": "Draft saved for human review.",
                }
            except (json.JSONDecodeError, TypeError):
                return {"status": "drafted", "raw": text}
        return {"status": "drafted"}
    except Exception as e:
        logger.error("failed to persist draft audit log: %s", e)
        return {"error": f"Failed to persist draft: {e}"}


def validate_sql_query(sql: str) -> str | None:
    """Return error message if SQL contains write statements, else None."""
    if _SQL_WRITE.search(sql):
        return "Only SELECT queries are allowed. Write operations are blocked."
    return None


def sql_guard_filter(tool_name: str, args: dict) -> dict | None:
    """Pre-invocation guard — blocks write SQL in any data-query tool.

    Returns a dict error response if blocked, None to allow.
    Used as a tool call interceptor in the graph's tool node.

    Scans GUARDED_TOOLS by name, and also checks any string argument
    that looks like SQL regardless of tool name (defense-in-depth).
    """
    sql = ""
    if tool_name in GUARDED_TOOLS:
        sql = args.get("query", "") or args.get("sql", "")
    else:
        for val in args.values():
            if isinstance(val, str) and _SQL_WRITE.search(val):
                sql = val
                break

    if not sql:
        return None

    error = validate_sql_query(sql)
    if error:
        logger.warning("Blocked write SQL in %s: %s", tool_name, sql[:200])
        return {"error": error}
    return None


def build_tools() -> list:
    """Return the list of local LangChain tools for the assistant.

    publish_audit_log is NOT included — it is called by the
    publish_draft graph node, not by the LLM directly.
    """
    return []
