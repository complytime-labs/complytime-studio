# 0029 — Notifications Belong Outside the Gateway

**Status:** Accepted
**Date:** 2026-05-14

## Context

The gateway previously owned a `notifications` table and REST endpoints (`/api/notifications`, `/api/notifications/unread-count`, `PATCH /api/notifications/{id}/read`). A NATS subscriber created notification rows when evidence or draft audit log events fired.

This was removed during the modulith simplification (see commit `8d515c1`). The UI components that consumed these endpoints degrade silently (empty feeds, zero counts).

## Decision

Notifications are a **presentation concern**, not a data platform concern. The gateway's role is to store evidence, certify it, and publish events. It should not own:

- User-facing notification state (read/unread tracking)
- Delivery preferences (in-app, email, Slack)
- Notification formatting or severity classification

## Candidate Homes

| Option | Fit | Trade-off |
|:--|:--|:--|
| **Studio Workbench** (complytime-studio) | Already owns agent UX; can subscribe to NATS and push to UI via SSE/WebSocket | Couples notification delivery to agent infrastructure |
| **Dedicated notification service** | Clean separation; multi-channel (email, Slack, webhook) | New service to deploy and maintain |
| **Studio UI server-side** | Nginx SSE sidecar subscribing to NATS directly | Minimal, but limited to in-app only |

The workbench is the preferred first candidate. It already has a WebSocket/SSE path to the UI for chat streaming and could reuse that channel for notifications.

## Consequences

- Gateway publishes NATS events (`core.evidence.*`, `core.draft.*`) — no change needed.
- UI notification components remain in `studio-ui` but are inert until a notification source is wired.
- Migration `013_drop_notifications.sql` removed the table. A new table in the workbench's own storage (or a lightweight in-memory store) would replace it.
- No timeline commitment. This is a "when needed" decision.
