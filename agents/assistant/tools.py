# SPDX-License-Identifier: Apache-2.0

"""Gateway tool functions and SQL guard for the ComplyTime Studio assistant.

@tool-decorated functions call the gateway REST API (or gRPC when
GATEWAY_GRPC_URL is set) to read platform data. MCP is used only
for gemara validation/migration.

SQL guard logic is applied as a pre-invocation check on any tool that
accepts raw SQL arguments. Protects against write operations regardless
of which MCP server exposes the tool.
"""

import json
import logging
import os
import re

import httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)

GEMARA_MCP_URL = os.environ.get("GEMARA_MCP_URL", "")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://studio-gateway:8080")
GATEWAY_GRPC_URL = os.environ.get("GATEWAY_GRPC_URL", "")
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


@tool
async def query_evidence(policy_id: str = "", target: str = "", limit: int = 100) -> str:
    """Query evidence records from the gateway, optionally filtered by policy and target."""
    params = {}
    if policy_id:
        params["policy_id"] = policy_id
    if target:
        params["target"] = target
    if limit:
        params["limit"] = str(limit)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GATEWAY_URL.rstrip('/')}/api/evidence",
            params=params,
            headers={"X-Forwarded-Email": AGENT_ID + "@complytime.dev"},
        )
        resp.raise_for_status()
        return resp.text


@tool
async def list_policies() -> str:
    """List all imported policies from the gateway."""
    if GATEWAY_GRPC_URL:
        return await _list_policies_grpc()
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GATEWAY_URL.rstrip('/')}/api/policies",
            headers={"X-Forwarded-Email": AGENT_ID + "@complytime.dev"},
        )
        resp.raise_for_status()
        return resp.text


async def _list_policies_grpc() -> str:
    """Call PolicyService.ListPolicies via gRPC and return JSON."""
    import grpc
    from google.protobuf.json_format import MessageToJson

    from complytime.v1 import policies_pb2, policies_pb2_grpc

    async with grpc.aio.insecure_channel(GATEWAY_GRPC_URL) as channel:
        stub = policies_pb2_grpc.PolicyServiceStub(channel)
        resp = await stub.ListPolicies(policies_pb2.ListPoliciesRequest())
        return MessageToJson(resp, preserving_proto_field_name=True)


@tool
async def get_certifications(policy_id: str = "", evidence_id: str = "") -> str:
    """Get certification records, optionally filtered by policy or evidence ID."""
    params = {}
    if policy_id:
        params["policy_id"] = policy_id
    if evidence_id:
        params["evidence_id"] = evidence_id
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GATEWAY_URL.rstrip('/')}/api/certifications",
            params=params,
            headers={"X-Forwarded-Email": AGENT_ID + "@complytime.dev"},
        )
        resp.raise_for_status()
        return resp.text


@tool
async def list_catalogs(catalog_type: str = "") -> str:
    """List catalogs from the gateway, optionally filtered by type."""
    params = {}
    if catalog_type:
        params["type"] = catalog_type
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{GATEWAY_URL.rstrip('/')}/api/catalogs",
            params=params,
            headers={"X-Forwarded-Email": AGENT_ID + "@complytime.dev"},
        )
        resp.raise_for_status()
        return resp.text


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
    user_email: str = "",
) -> dict:
    """Publish a validated AuditLog YAML as a draft via the gateway API.

    Called by the publish_draft graph node AFTER the validation gate
    passes and human approval is received. Not directly callable by
    the LLM. Posts directly to the gateway's internal port so the
    draft is attributed to the real user (MCP stays read-only).
    """
    model_name = os.environ.get("MODEL_NAME", "unknown")
    identity = user_email or os.environ.get("MCP_IDENTITY", "studio-assistant@complytime.dev")
    body = {
        "policy_id": policy_id,
        "content": yaml_content,
        "agent_reasoning": reasoning,
        "model": model_name,
        "prompt_version": "langgraph-v1",
    }
    headers = {
        "Content-Type": "application/json",
        "X-Forwarded-Email": identity,
    }

    try:
        url = GATEWAY_URL.rstrip("/") + "/api/draft-audit-logs"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            result = resp.json()
            draft_id = result.get("draft_id", "")
            logger.info("persisted draft audit log %s (policy=%s)", draft_id, policy_id)
            return {
                "status": "drafted",
                "draft_id": draft_id,
                "note": "Draft saved for human review.",
            }
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
    return [query_evidence, list_policies, get_certifications, list_catalogs]
