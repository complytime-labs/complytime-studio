# SPDX-License-Identifier: Apache-2.0

"""In-memory notifications fed by NATS core events (see ADR #0029)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

CORE_EVENTS_PREFIX = "core.events."
NATS_CORE_EVENTS_SUBJECT = "core.events.>"
ENV_NATS_URL = "NATS_URL"
JSON_KEY_POLICY_ID = "policy_id"

KEY_NOTIFICATION_ID = "notification_id"
KEY_READ = "read"

QUERY_UNREAD_ONLY = "unread"
QUERY_LIMIT = "limit"
QUERY_UNREAD_TRUE = "true"

DEFAULT_LIST_LIMIT = 50
MAX_NOTIFICATIONS = 1000
MAX_PAYLOAD_BYTES = 4096

_notifications: list[dict[str, Any]] = []
_notification_store_lock = asyncio.Lock()


@dataclass
class Notification:
    notification_id: str
    type: str
    policy_id: str
    payload: str
    read: bool
    created_at: str


def notification_type_from_subject(subject: str) -> str:
    """Map NATS subject suffix to notification type (e.g. core.events.foo -> foo)."""
    if subject.startswith(CORE_EVENTS_PREFIX):
        return subject[len(CORE_EVENTS_PREFIX) :]
    return subject


def clear_notification_store_for_tests() -> None:
    """Clear all notifications (tests only; no lock when NATS subscriber is off)."""
    _notifications.clear()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_notification(entry: dict[str, Any]) -> None:
    _notifications.append(entry)
    overflow = len(_notifications) - MAX_NOTIFICATIONS
    if overflow > 0:
        del _notifications[0:overflow]


async def seed_notification(notification: Notification) -> None:
    """Append a notification row (primarily tests)."""
    async with _notification_store_lock:
        _append_notification(asdict(notification))


async def _ingest_nats_message(msg: Any) -> None:
    subject = getattr(msg, "subject", "") or ""
    raw_bytes = getattr(msg, "data", b"") or b""
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raw = raw_bytes.decode("utf-8", errors="replace")
    if len(raw) > MAX_PAYLOAD_BYTES:
        raw = raw[:MAX_PAYLOAD_BYTES]
    notification_type = notification_type_from_subject(subject)
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    policy_id = ""
    if isinstance(parsed, dict):
        pid = parsed.get(JSON_KEY_POLICY_ID)
        policy_id = str(pid) if pid is not None else ""
    notification = Notification(
        notification_id=str(uuid.uuid4()),
        type=notification_type,
        policy_id=policy_id,
        payload=raw,
        read=False,
        created_at=_iso_now(),
    )
    entry = asdict(notification)
    async with _notification_store_lock:
        _append_notification(entry)


async def start_nats_subscriber() -> None:
    """Connect to NATS and subscribe to all core events; no-op if disabled or nats missing."""
    nats_url = os.environ.get(ENV_NATS_URL, "").strip()
    if not nats_url:
        logger.warning("%s not set - notifications disabled", ENV_NATS_URL)
        return
    try:
        import nats  # noqa: PLC0415 - deferred import; optional dependency
    except ImportError:
        logger.warning("nats-py not installed - notifications subscriber disabled")
        return

    try:
        nc = await nats.connect(nats_url)
        sub = await nc.subscribe(NATS_CORE_EVENTS_SUBJECT)
        async for msg in sub.messages:
            try:
                await _ingest_nats_message(msg)
            except Exception:
                logger.exception("Failed to ingest NATS message on %s", msg.subject)
    except Exception:
        logger.exception("NATS subscriber failed")


def _parse_limit(param: str | None) -> int | None:
    if param is None:
        return DEFAULT_LIST_LIMIT
    try:
        return int(param)
    except ValueError:
        return None


async def list_notifications(request: Request) -> JSONResponse:
    """GET /workbench/notifications — list notifications, optionally filter by unread."""
    unread_only = request.query_params.get(QUERY_UNREAD_ONLY) == QUERY_UNREAD_TRUE
    limit = _parse_limit(request.query_params.get(QUERY_LIMIT))
    if limit is None or limit < 1:
        return JSONResponse({"error": "invalid limit"}, status_code=400)
    limit = min(limit, MAX_NOTIFICATIONS)

    async with _notification_store_lock:
        snapshot = list(_notifications)
    items = snapshot if not unread_only else [n for n in snapshot if not n[KEY_READ]]
    return JSONResponse(items[:limit])


async def unread_count(_request: Request) -> JSONResponse:
    """GET /workbench/notifications/unread-count"""
    async with _notification_store_lock:
        count = sum(1 for n in _notifications if not n[KEY_READ])
    return JSONResponse({"count": count})


async def mark_read(request: Request) -> JSONResponse:
    """PATCH /workbench/notifications/{id}/read"""
    nid = request.path_params["id"]
    async with _notification_store_lock:
        for n in _notifications:
            if n[KEY_NOTIFICATION_ID] == nid:
                n[KEY_READ] = True
                return JSONResponse({"status": "ok"})
    return JSONResponse({"error": "not found"}, status_code=404)
