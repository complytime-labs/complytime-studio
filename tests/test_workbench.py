# SPDX-License-Identifier: Apache-2.0
#
# Integration tests for the Studio Workbench HTTP endpoints.
# Uses httpx ASGI transport — no running server needed.

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

pytestmark = pytest.mark.asyncio


class TestAgentDirectory:
    async def test_empty_directory(self, workbench_client: httpx.AsyncClient):
        resp = await workbench_client.get("/workbench/agents")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_directory_with_agents(
        self, monkeypatch, workbench_client: httpx.AsyncClient
    ):
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

    async def test_directory_malformed_json(
        self, monkeypatch, workbench_client: httpx.AsyncClient
    ):
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
    async def test_unavailable_without_gemara_mcp(
        self, monkeypatch, workbench_client: httpx.AsyncClient
    ):
        monkeypatch.setenv("GEMARA_MCP_URL", "")
        resp = await workbench_client.post(
            "/workbench/validate",
            json={"yaml": "foo: bar", "definition": "#ControlCatalog"},
        )
        assert resp.status_code == 503


class TestMigrateEndpoint:
    async def test_unavailable_without_gemara_mcp(
        self, monkeypatch, workbench_client: httpx.AsyncClient
    ):
        monkeypatch.setenv("GEMARA_MCP_URL", "")
        resp = await workbench_client.post(
            "/workbench/migrate",
            json={"yaml": "foo: bar"},
        )
        assert resp.status_code == 503


def _mock_gateway_response(json_data, status_code=200):
    resp = httpx.Response(
        status_code, json=json_data, request=httpx.Request("GET", "http://gw")
    )
    return resp


class TestPostureEndpoint:
    async def test_aggregates_evidence_by_policy(
        self, workbench_client: httpx.AsyncClient
    ):
        policies = [
            {
                "policy_id": "p1",
                "title": "Policy A",
                "version": "1.0",
                "owner": "alice",
            },
        ]
        evidence = [
            {
                "policy_id": "p1",
                "eval_result": "Passed",
                "collected_at": "2026-06-01T00:00:00Z",
                "target_id": "t1",
                "control_id": "c1",
            },
            {
                "policy_id": "p1",
                "eval_result": "Failed",
                "collected_at": "2026-06-02T00:00:00Z",
                "target_id": "t1",
                "control_id": "c2",
            },
            {
                "policy_id": "p1",
                "eval_result": "Passed",
                "collected_at": "2026-06-03T00:00:00Z",
                "target_id": "t2",
                "control_id": "c1",
            },
        ]

        async def mock_get(url, **kwargs):
            if "/api/policies" in str(url):
                return _mock_gateway_response(policies)
            return _mock_gateway_response(evidence)

        with patch("workbench.app.httpx.AsyncClient") as mock_cls:
            ctx = AsyncMock()
            ctx.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await workbench_client.get("/workbench/posture")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        row = data[0]
        assert row["policy_id"] == "p1"
        assert row["total_rows"] == 3
        assert row["passed_rows"] == 2
        assert row["failed_rows"] == 1
        assert row["other_rows"] == 0
        assert row["target_count"] == 2
        assert row["control_count"] == 2
        assert row["latest_evidence_at"] == "2026-06-03T00:00:00Z"

    async def test_ignores_evidence_for_unknown_policy(
        self, workbench_client: httpx.AsyncClient
    ):
        policies = [{"policy_id": "p1", "title": "Known", "version": "1.0"}]
        evidence = [
            {
                "policy_id": "p1",
                "eval_result": "Passed",
                "target_id": "t1",
                "control_id": "c1",
            },
            {
                "policy_id": "unknown",
                "eval_result": "Passed",
                "target_id": "t2",
                "control_id": "c2",
            },
        ]

        async def mock_get(url, **kwargs):
            if "/api/policies" in str(url):
                return _mock_gateway_response(policies)
            return _mock_gateway_response(evidence)

        with patch("workbench.app.httpx.AsyncClient") as mock_cls:
            ctx = AsyncMock()
            ctx.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await workbench_client.get("/workbench/posture")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["total_rows"] == 1

    async def test_empty_policies_returns_empty(
        self, workbench_client: httpx.AsyncClient
    ):
        async def mock_get(url, **kwargs):
            return _mock_gateway_response([])

        with patch("workbench.app.httpx.AsyncClient") as mock_cls:
            ctx = AsyncMock()
            ctx.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await workbench_client.get("/workbench/posture")

        assert resp.status_code == 200
        assert resp.json() == []


class TestRiskSeverityEndpoint:
    async def test_requires_policy_id(self, workbench_client: httpx.AsyncClient):
        resp = await workbench_client.get("/workbench/risks/severity")
        assert resp.status_code == 400
        assert "policy_id required" in resp.json()["error"]

    async def test_aggregates_max_severity_per_control(
        self, workbench_client: httpx.AsyncClient
    ):
        risks = [
            {"risk_id": "r1", "catalog_id": "cat1", "severity": "low"},
            {"risk_id": "r2", "catalog_id": "cat1", "severity": "high"},
        ]
        risk_threats = [
            {
                "risk_id": "r1",
                "catalog_id": "cat1",
                "threat_reference_id": "tr1",
                "threat_entry_id": "te1",
            },
            {
                "risk_id": "r2",
                "catalog_id": "cat1",
                "threat_reference_id": "tr1",
                "threat_entry_id": "te1",
            },
        ]
        control_threats = [
            {
                "control_id": "ctrl-1",
                "threat_reference_id": "tr1",
                "threat_entry_id": "te1",
            },
        ]

        async def mock_get(url, **kwargs):
            if "/api/risks" in str(url) and "/api/risk-threats" not in str(url):
                return _mock_gateway_response(risks)
            if "/api/risk-threats" in str(url):
                return _mock_gateway_response(risk_threats)
            if "/api/control-threats" in str(url):
                return _mock_gateway_response(control_threats)
            return _mock_gateway_response([])

        with patch("workbench.app.httpx.AsyncClient") as mock_cls:
            ctx = AsyncMock()
            ctx.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await workbench_client.get("/workbench/risks/severity?policy_id=p1")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["control_id"] == "ctrl-1"
        assert data[0]["max_severity"] == "high"
        assert data[0]["risk_count"] == 2

    async def test_no_matching_threats_returns_empty(
        self, workbench_client: httpx.AsyncClient
    ):
        async def mock_get(url, **kwargs):
            return _mock_gateway_response([])

        with patch("workbench.app.httpx.AsyncClient") as mock_cls:
            ctx = AsyncMock()
            ctx.get = mock_get
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=ctx)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            resp = await workbench_client.get("/workbench/risks/severity?policy_id=p1")

        assert resp.status_code == 200
        assert resp.json() == []
