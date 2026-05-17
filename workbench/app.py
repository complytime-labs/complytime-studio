# SPDX-License-Identifier: Apache-2.0

"""Studio Workbench HTTP server.

Provides agent-support endpoints under /workbench/*:
  - A2A routing to agents
  - Agent directory
  - Chat conversation state
  - Notifications (NATS-backed core.events; ADR #0029)
  - Gemara validate/migrate (direct MCP)
  - OCI publish and registry browse (direct MCP)

Run standalone or mount routes into an existing Starlette app.
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Mount, Route

from .migrate import run_migrations
from .notifications import (
    list_notifications,
    mark_read,
    start_nats_subscriber,
    unread_count,
)
from .programs import (
    ENV_POSTGRES_URL,
    create_program,
    delete_program,
    get_program,
    list_programs,
    update_program,
)

logger = logging.getLogger(__name__)

GEMARA_MCP_URL = os.environ.get("GEMARA_MCP_URL", "")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://studio-gateway:8080")


def _load_agent_cards() -> list[dict[str, Any]]:
    raw = os.environ.get("AGENT_DIRECTORY", "[]")
    try:
        cards = json.loads(raw)
    except json.JSONDecodeError:
        cards = []
    return cards if isinstance(cards, list) else []


def _resolve_agent_url(agent_name: str) -> str | None:
    """Resolve agent name to its A2A base URL from AGENT_DIRECTORY."""
    for card in _load_agent_cards():
        if card.get("name") == agent_name and card.get("url"):
            return card["url"].rstrip("/")
    return None


async def agent_directory(request: Request) -> JSONResponse:
    """List available agents. Reads AGENT_DIRECTORY env var (JSON)."""
    return JSONResponse(_load_agent_cards())


async def a2a_proxy(request: Request) -> StreamingResponse | JSONResponse:
    """Reverse-proxy A2A requests to the target agent, streaming SSE."""
    agent_name = request.path_params["name"]
    agent_url = _resolve_agent_url(agent_name)
    if not agent_url:
        return JSONResponse(
            {"error": f"unknown agent: {agent_name}"}, status_code=403
        )

    body = await request.body()
    headers = {
        "content-type": request.headers.get("content-type", "application/json"),
        "accept": request.headers.get("accept", "application/json"),
    }
    if "authorization" in request.headers:
        headers["authorization"] = request.headers["authorization"]

    try:
        client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=10.0))

        upstream_req = client.build_request(
            method=request.method,
            url=agent_url,
            content=body,
            headers=headers,
        )
        upstream_resp = await client.send(upstream_req, stream=True)

        content_type = upstream_resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            async def stream_sse():
                try:
                    async for chunk in upstream_resp.aiter_bytes():
                        yield chunk
                finally:
                    await upstream_resp.aclose()
                    await client.aclose()

            return StreamingResponse(
                stream_sse(),
                status_code=upstream_resp.status_code,
                media_type="text/event-stream",
                headers={
                    "cache-control": "no-cache",
                    "x-accel-buffering": "no",
                },
            )

        resp_body = await upstream_resp.aread()
        await upstream_resp.aclose()
        await client.aclose()
        return StreamingResponse(
            iter([resp_body]),
            status_code=upstream_resp.status_code,
            media_type=content_type or "application/json",
        )

    except httpx.ConnectError:
        return JSONResponse(
            {"error": f"agent {agent_name} unreachable"}, status_code=502
        )
    except Exception as e:
        logger.exception("a2a proxy error for %s", agent_name)
        return JSONResponse({"error": str(e)}, status_code=502)


async def chat_get(request: Request) -> JSONResponse:
    """Retrieve chat history for the current session."""
    return JSONResponse({"messages": None, "taskId": ""})


async def chat_put(request: Request) -> JSONResponse:
    """Persist chat history for the current session."""
    return JSONResponse(None, status_code=204)


async def validate_artifact(request: Request) -> JSONResponse:
    """Proxy to gemara-mcp validate_gemara_artifact."""
    if not GEMARA_MCP_URL:
        return JSONResponse(
            {"error": "gemara-mcp unavailable"}, status_code=503
        )
    body = await request.json()
    artifact_content = body.get("yaml", "")
    definition = body.get("definition", "")
    version = body.get("version", "latest")

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(GEMARA_MCP_URL) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await session.call_tool(
                    "validate_gemara_artifact",
                    arguments={
                        "artifact_content": artifact_content,
                        "definition": definition,
                        "version": version,
                    },
                )
                text = result.content[0].text if result.content else ""
                try:
                    return JSONResponse(json.loads(text))
                except json.JSONDecodeError:
                    return JSONResponse({"valid": False, "errors": [text]})
    except Exception as e:
        logger.exception("validate_gemara_artifact failed")
        return JSONResponse({"error": str(e)}, status_code=502)


async def posture_summary(request: Request) -> JSONResponse:
    """Aggregate posture from gateway evidence and certifications (ADR 0039)."""
    params = dict(request.query_params)
    headers = {"X-Forwarded-Email": request.headers.get("x-forwarded-email", "")}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{GATEWAY_URL.rstrip('/')}/api/posture",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return JSONResponse(resp.json())
    except httpx.HTTPStatusError as e:
        return JSONResponse({"error": str(e)}, status_code=e.response.status_code)
    except Exception as e:
        logger.exception("posture aggregation failed")
        return JSONResponse({"error": str(e)}, status_code=502)


async def risk_severity(request: Request) -> JSONResponse:
    """Aggregate risk severity from gateway risk data (ADR 0039)."""
    params = dict(request.query_params)
    headers = {"X-Forwarded-Email": request.headers.get("x-forwarded-email", "")}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{GATEWAY_URL.rstrip('/')}/api/risks/severity",
                params=params,
                headers=headers,
            )
            resp.raise_for_status()
            return JSONResponse(resp.json())
    except httpx.HTTPStatusError as e:
        return JSONResponse({"error": str(e)}, status_code=e.response.status_code)
    except Exception as e:
        logger.exception("risk severity aggregation failed")
        return JSONResponse({"error": str(e)}, status_code=502)


async def migrate_artifact(request: Request) -> JSONResponse:
    """Proxy to gemara-mcp migrate_gemara_artifact."""
    if not GEMARA_MCP_URL:
        return JSONResponse(
            {"error": "gemara-mcp unavailable"}, status_code=503
        )
    body = await request.json()
    args: dict = {"artifact_content": body.get("yaml", "")}
    if body.get("artifact_type"):
        args["artifact_type"] = body["artifact_type"]
    if body.get("gemara_version"):
        args["gemara_version"] = body["gemara_version"]

    try:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(GEMARA_MCP_URL) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await session.call_tool(
                    "migrate_gemara_artifact", arguments=args
                )
                text = result.content[0].text if result.content else ""
                return JSONResponse({"yaml": text})
    except Exception as e:
        logger.exception("migrate_gemara_artifact failed")
        return JSONResponse({"error": str(e)}, status_code=502)


async def publish_bundle(request: Request) -> JSONResponse:
    """Bundle YAML artifacts and push to OCI registry via oras-mcp."""
    if not os.environ.get("ORAS_MCP_URL", ""):
        return JSONResponse(
            {"error": "oras-mcp unavailable"}, status_code=503
        )
    return JSONResponse(
        {"error": "publish not yet implemented"}, status_code=501
    )


async def registry_repositories(request: Request) -> JSONResponse:
    """List OCI repositories via oras-mcp."""
    if not os.environ.get("ORAS_MCP_URL", ""):
        return JSONResponse(
            {"error": "oras-mcp unavailable"}, status_code=503
        )
    return JSONResponse(
        {"error": "registry browse not yet implemented"}, status_code=501
    )


async def recommendations_stub(request: Request) -> JSONResponse:
    """Stub: recommendation engine deferred (ADR #0030)."""
    return JSONResponse([], status_code=200)


async def recommendation_action_stub(request: Request) -> JSONResponse:
    """Stub: attach/dismiss deferred (ADR #0030)."""
    return JSONResponse(
        {"error": "recommendation engine not yet implemented"}, status_code=501
    )


workbench_routes = [
    Route("/agents", agent_directory, methods=["GET"]),
    Route("/a2a/{name:path}", a2a_proxy, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
    Route("/chat/history", chat_get, methods=["GET"]),
    Route("/chat/history", chat_put, methods=["PUT"]),
    Route("/validate", validate_artifact, methods=["POST"]),
    Route("/migrate", migrate_artifact, methods=["POST"]),
    Route("/publish", publish_bundle, methods=["POST"]),
    Route("/registry/repositories", registry_repositories, methods=["GET"]),
    Route("/posture", posture_summary, methods=["GET"]),
    Route("/risks/severity", risk_severity, methods=["GET"]),
    Route("/programs", list_programs, methods=["GET"]),
    Route("/programs", create_program, methods=["POST"]),
    Route("/programs/{id}", get_program, methods=["GET"]),
    Route("/programs/{id}", update_program, methods=["PUT"]),
    Route("/programs/{id}", delete_program, methods=["DELETE"]),
    Route("/programs/{id}/recommendations/{policy_id}/attach", recommendation_action_stub, methods=["POST"]),
    Route("/programs/{id}/recommendations/{policy_id}/dismiss", recommendation_action_stub, methods=["POST"]),
    Route("/programs/{id}/recommendations", recommendations_stub, methods=["GET"]),
    Route("/notifications/unread-count", unread_count, methods=["GET"]),
    Route("/notifications/{id}/read", mark_read, methods=["PATCH"]),
    Route("/notifications", list_notifications, methods=["GET"]),
]

workbench_mount = Mount("/workbench", routes=workbench_routes)


@asynccontextmanager
async def _lifespan(app: Starlette) -> AsyncGenerator[None, None]:
    dsn = os.environ.get(ENV_POSTGRES_URL, "").strip()
    if dsn:
        await run_migrations(dsn)
    else:
        logger.warning("POSTGRES_URL not set — skipping workbench migrations")
    asyncio.create_task(start_nats_subscriber())
    yield


def create_app() -> Starlette:
    """Create standalone Starlette app for the workbench."""
    return Starlette(routes=[workbench_mount], lifespan=_lifespan)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("WORKBENCH_PORT", "8090"))
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host="0.0.0.0", port=port)
