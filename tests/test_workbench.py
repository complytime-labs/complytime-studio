# SPDX-License-Identifier: Apache-2.0
#
# Integration tests for the Studio Workbench HTTP endpoints.
# Uses httpx ASGI transport — no running server needed.

import json
import os

import httpx
import pytest

pytestmark = pytest.mark.asyncio


class TestAgentDirectory:
    async def test_empty_directory(self, workbench_client: httpx.AsyncClient):
        resp = await workbench_client.get("/workbench/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_directory_with_agents(self, monkeypatch, workbench_client: httpx.AsyncClient):
        cards = [
            {
                "name": "test-agent",
                "description": "A test agent",
                "url": "http://localhost:8080/",
                "skills": [{"id": "test", "name": "Test Skill"}],
            }
        ]
        monkeypatch.setenv("AGENT_DIRECTORY", json.dumps(cards))
        resp = await workbench_client.get("/workbench/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-agent"

    async def test_directory_malformed_json(self, monkeypatch, workbench_client: httpx.AsyncClient):
        monkeypatch.setenv("AGENT_DIRECTORY", "{not json")
        resp = await workbench_client.get("/workbench/agents")
        assert resp.status_code == 200
        assert resp.json() == []


class TestChatHistory:
    async def test_get_returns_empty_state(self, workbench_client: httpx.AsyncClient):
        resp = await workbench_client.get("/workbench/chat/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "messages" in data
        assert "taskId" in data

    async def test_put_returns_204(self, workbench_client: httpx.AsyncClient):
        resp = await workbench_client.put(
            "/workbench/chat/history",
            json={"messages": [], "taskId": "test-123"},
        )
        assert resp.status_code == 204


class TestA2AProxy:
    async def test_unknown_agent_returns_403(self, workbench_client: httpx.AsyncClient):
        resp = await workbench_client.post(
            "/workbench/a2a/nonexistent-agent",
            json={"jsonrpc": "2.0", "method": "tasks/send", "id": 1},
        )
        assert resp.status_code == 403
        assert "unknown agent" in resp.json()["error"]


class TestValidateEndpoint:
    async def test_unavailable_without_gemara_mcp(self, monkeypatch, workbench_client: httpx.AsyncClient):
        monkeypatch.setenv("GEMARA_MCP_URL", "")
        resp = await workbench_client.post(
            "/workbench/validate",
            json={"yaml": "foo: bar", "definition": "#ControlCatalog"},
        )
        assert resp.status_code == 503


class TestMigrateEndpoint:
    async def test_unavailable_without_gemara_mcp(self, monkeypatch, workbench_client: httpx.AsyncClient):
        monkeypatch.setenv("GEMARA_MCP_URL", "")
        resp = await workbench_client.post(
            "/workbench/migrate",
            json={"yaml": "foo: bar"},
        )
        assert resp.status_code == 503


class TestPublishEndpoint:
    async def test_unavailable_without_oras_mcp(self, monkeypatch, workbench_client: httpx.AsyncClient):
        monkeypatch.setenv("ORAS_MCP_URL", "")
        resp = await workbench_client.post(
            "/workbench/publish",
            json={"artifacts": []},
        )
        assert resp.status_code == 503


class TestRegistryEndpoint:
    async def test_unavailable_without_oras_mcp(self, monkeypatch, workbench_client: httpx.AsyncClient):
        monkeypatch.setenv("ORAS_MCP_URL", "")
        resp = await workbench_client.get("/workbench/registry/repositories")
        assert resp.status_code == 503
