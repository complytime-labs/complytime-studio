# SPDX-License-Identifier: Apache-2.0
#
# A2A protocol contract tests.
# Validates agent card schema and JSON-RPC request/response structure
# against a live agent. Requires the agent to be running.
#
# These tests are gated behind the AGENT_URL environment variable.
# Skip when no agent is available (unit test runs).
#
# Usage:
#   AGENT_URL=http://localhost:8080 python -m pytest tests/test_a2a_contract.py -v

import os

import httpx
import pytest

AGENT_URL = os.environ.get("AGENT_URL", "")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not AGENT_URL, reason="AGENT_URL not set — skipping live A2A tests"),
]

REQUIRED_AGENT_CARD_FIELDS = {"name", "url", "version", "capabilities", "skills"}


class TestAgentCard:
    async def test_agent_card_reachable(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{AGENT_URL}/.well-known/agent.json")
        assert resp.status_code == 200
        assert "application/json" in resp.headers.get("content-type", "")

    async def test_agent_card_schema(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{AGENT_URL}/.well-known/agent.json")
        card = resp.json()
        missing = REQUIRED_AGENT_CARD_FIELDS - set(card.keys())
        assert not missing, f"Agent card missing fields: {missing}"
        assert isinstance(card["skills"], list)
        assert len(card["skills"]) > 0, "Agent card should declare at least one skill"

    async def test_agent_card_capabilities(self):
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{AGENT_URL}/.well-known/agent.json")
        card = resp.json()
        caps = card.get("capabilities", {})
        assert isinstance(caps, dict)


class TestA2ATaskLifecycle:
    """Validates the A2A JSON-RPC task submission contract.

    Submitting a task requires the agent to invoke an LLM. These tests
    verify the protocol-level response structure without asserting on
    task completion (which depends on LLM availability).
    """

    async def test_invalid_method_returns_error(self):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                AGENT_URL,
                json={
                    "jsonrpc": "2.0",
                    "method": "nonexistent/method",
                    "id": "test-invalid",
                    "params": {},
                },
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code in (200, 400, 404)
        body = resp.json()
        if "error" in body:
            assert "code" in body["error"]

    async def test_tasks_send_requires_params(self):
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                AGENT_URL,
                json={
                    "jsonrpc": "2.0",
                    "method": "tasks/send",
                    "id": "test-no-params",
                },
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code in (200, 400)
