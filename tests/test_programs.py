# SPDX-License-Identifier: Apache-2.0

"""Programs CRUD endpoint tests with mocked Postgres pool."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

import httpx
import pytest

pytestmark = pytest.mark.asyncio


class _AcquireConn:
    """Minimal async context manager for mocked pool.acquire()."""

    def __init__(self, conn: MagicMock | AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> MagicMock | AsyncMock:
        return self._conn

    async def __aexit__(self, *exc: object) -> None:
        return None


def _mock_pool(conn: MagicMock | AsyncMock) -> MagicMock:
    pool = MagicMock()

    def _acquire() -> _AcquireConn:
        return _AcquireConn(conn)

    pool.acquire = _acquire
    return pool


@pytest.fixture
def program_row_base() -> dict:
    pid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    return {
        "id": pid,
        "name": "Program A",
        "guidance_catalog_id": None,
        "framework": "fedramp",
        "applicability": [],
        "status": "intake",
        "health": None,
        "owner": None,
        "description": None,
        "metadata": {},
        "policy_ids": [],
        "environments": [],
        "version": 1,
        "green_pct": 90,
        "red_pct": 50,
        "score_pct": 0,
        "created_at": now,
        "updated_at": now,
    }


class TestProgramsList:
    async def test_list_returns_empty_when_none(
        self, monkeypatch: pytest.MonkeyPatch, workbench_client: httpx.AsyncClient
    ) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=[])
        pool = _mock_pool(mock_conn)
        monkeypatch.setattr(
            "workbench.programs.get_pool",
            AsyncMock(return_value=pool),
        )

        resp = await workbench_client.get("/workbench/programs")
        assert resp.status_code == 200
        assert resp.json() == []


class TestProgramsCreate:
    async def test_requires_name(
        self, workbench_client: httpx.AsyncClient
    ) -> None:
        resp = await workbench_client.post(
            "/workbench/programs",
            json={"framework": "fedramp"},
        )
        assert resp.status_code == 400
        assert "name" in resp.json()["error"]

    async def test_requires_framework(
        self, workbench_client: httpx.AsyncClient
    ) -> None:
        resp = await workbench_client.post(
            "/workbench/programs",
            json={"name": "P"},
        )
        assert resp.status_code == 400
        assert "framework" in resp.json()["error"]

    async def test_create_returns_201(
        self,
        monkeypatch: pytest.MonkeyPatch,
        workbench_client: httpx.AsyncClient,
        program_row_base: dict,
    ) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)
        mock_conn.fetchrow = AsyncMock(return_value=program_row_base)
        pool = _mock_pool(mock_conn)
        monkeypatch.setattr(
            "workbench.programs.get_pool",
            AsyncMock(return_value=pool),
        )

        resp = await workbench_client.post(
            "/workbench/programs",
            json={"name": "Program A", "framework": "fedramp"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Program A"
        assert body["framework"] == "fedramp"


class TestProgramsUpdate:
    async def test_wrong_version_returns_409(
        self, monkeypatch: pytest.MonkeyPatch, workbench_client: httpx.AsyncClient
    ) -> None:
        pid = str(uuid.uuid4())
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)
        mock_conn.fetchrow = AsyncMock(return_value=None)
        pool = _mock_pool(mock_conn)
        monkeypatch.setattr(
            "workbench.programs.get_pool",
            AsyncMock(return_value=pool),
        )

        resp = await workbench_client.put(
            f"/workbench/programs/{pid}",
            json={
                "name": "P",
                "framework": "fedramp",
                "status": "intake",
                "version": 99,
                "applicability": [],
                "policy_ids": [],
                "environments": [],
                "metadata": {},
                "green_pct": 90,
                "red_pct": 50,
            },
        )
        assert resp.status_code == 409
        assert "conflict" in resp.json()["error"]


class TestProgramsGet:
    async def test_unknown_id_returns_404(
        self, monkeypatch: pytest.MonkeyPatch, workbench_client: httpx.AsyncClient
    ) -> None:
        pid = str(uuid.uuid4())
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        pool = _mock_pool(mock_conn)
        monkeypatch.setattr(
            "workbench.programs.get_pool",
            AsyncMock(return_value=pool),
        )

        resp = await workbench_client.get(f"/workbench/programs/{pid}")
        assert resp.status_code == 404


class TestProgramsDelete:
    async def test_unknown_id_returns_404(
        self, monkeypatch: pytest.MonkeyPatch, workbench_client: httpx.AsyncClient
    ) -> None:
        pid = str(uuid.uuid4())
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        pool = _mock_pool(mock_conn)
        monkeypatch.setattr(
            "workbench.programs.get_pool",
            AsyncMock(return_value=pool),
        )

        resp = await workbench_client.delete(f"/workbench/programs/{pid}")
        assert resp.status_code == 404
