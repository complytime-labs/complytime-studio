# SPDX-License-Identifier: Apache-2.0
#
# Workbench notifications API tests (httpx ASGI transport).

import json
import uuid

import httpx
import pytest

from workbench.notifications import Notification, clear_notification_store_for_tests, seed_notification

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _notification_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NATS_URL", raising=False)
    clear_notification_store_for_tests()
    yield
    clear_notification_store_for_tests()


class TestNotificationsList:
    async def test_list_empty_initially(self, workbench_client: httpx.AsyncClient) -> None:
        resp = await workbench_client.get("/workbench/notifications")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_returns_seeded_notification(
        self, workbench_client: httpx.AsyncClient
    ) -> None:
        nid = str(uuid.uuid4())
        payload = json.dumps({"policy_id": "pol-1", "detail": "x"})
        await seed_notification(
            Notification(
                notification_id=nid,
                type="evidence_arrival",
                policy_id="pol-1",
                payload=payload,
                read=False,
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        resp = await workbench_client.get("/workbench/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["notification_id"] == nid
        assert data[0]["type"] == "evidence_arrival"
        assert data[0]["policy_id"] == "pol-1"


class TestUnreadCount:
    async def test_unread_count_zero_initially(self, workbench_client: httpx.AsyncClient) -> None:
        resp = await workbench_client.get("/workbench/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json() == {"count": 0}

    async def test_unread_decreases_after_mark_read(
        self, workbench_client: httpx.AsyncClient
    ) -> None:
        nid = str(uuid.uuid4())
        await seed_notification(
            Notification(
                notification_id=nid,
                type="draft_created",
                policy_id="",
                payload="{}",
                read=False,
                created_at="2026-01-01T00:00:00+00:00",
            )
        )
        assert (
            await workbench_client.get("/workbench/notifications/unread-count")
        ).json() == {"count": 1}

        mr = await workbench_client.patch(f"/workbench/notifications/{nid}/read")
        assert mr.status_code == 200

        assert (
            await workbench_client.get("/workbench/notifications/unread-count")
        ).json() == {"count": 0}


class TestMarkRead:
    async def test_mark_read_unknown_returns_404(
        self, workbench_client: httpx.AsyncClient
    ) -> None:
        resp = await workbench_client.patch("/workbench/notifications/bad-id/read")
        assert resp.status_code == 404
        assert resp.json()["error"] == "not found"
