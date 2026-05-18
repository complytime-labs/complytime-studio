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

## NATS Wiring Plan

The gateway already publishes to NATS for ingest (`core.ingest`). Extend with event subjects:

| Subject | Publisher | Payload |
|:--|:--|:--|
| `core.events.evidence_arrival` | Gateway (post-ingest worker) | `{policy_id, artifact_type, job_id}` |
| `core.events.posture_change` | Gateway (certifier pipeline) | `{policy_id, previous_rate, current_rate}` |
| `core.events.draft_created` | Gateway (draft audit log handler) | `{draft_id, policy_id}` |

The workbench subscribes to `core.events.>` and stores notifications in memory (capped at 1000 entries). The UI polls the REST API below.

**MVP scope (current):** In-memory store, REST polling. Notifications are ephemeral signals — the underlying data (evidence, posture, drafts) is already persisted in core. Restarts clear the notification list; this is acceptable for single-replica workbench.

**Future (evaluate when needed):** Persistent `workbench.notifications` table, SSE/WebSocket push to UI, multi-channel delivery (email, Slack).

### Workbench notification API

```
GET    /workbench/notifications
GET    /workbench/notifications/unread-count
PATCH  /workbench/notifications/{id}/read
```

Studio UI notification components update to call `/workbench/*` paths instead of `/api/*`.

## Consequences

- Gateway publishes NATS events — no notification state, no read/unread tracking.
- Workbench owns notification storage, formatting, severity classification, and delivery.
- UI notification components call `/workbench/notifications*` endpoints.
- MVP uses in-memory storage — no migration, no persistence across restarts.
- Migration `013_drop_notifications.sql` removed the gateway table. A persistent `workbench.notifications` table is deferred until multi-replica or compliance requirements emerge.
