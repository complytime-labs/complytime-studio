<!-- SPDX-License-Identifier: Apache-2.0 -->

# ComplyTime Studio Workbench Architecture

Python service providing agent support, A2A routing, and compliance tooling. Runs alongside the data platform gateway as a separate deployment.

## Stack

| Layer | Tech |
|:--|:--|
| HTTP | Starlette (ASGI) |
| Agent framework | LangGraph |
| Agent protocol | A2A (Agent-to-Agent) |
| Agent management | kagent (BYO agent CRD) |
| MCP clients | gemara-mcp, oras-mcp, complytime-mcp |
| Checkpointer | PostgresSaver (psycopg + connection pool) |

## Components

### Workbench HTTP Server

Starlette app serving `/workbench/*` routes:

| Path | Purpose |
|:--|:--|
| `/workbench/agents` | Agent directory — lists available agents and skills |
| `/workbench/a2a/*` | A2A protocol proxy to agents (SSE streaming) |
| `/workbench/chat/*` | Chat conversation state (create, list, get) |
| `/workbench/validate` | Gemara artifact validation (via gemara-mcp) |
| `/workbench/migrate` | Gemara artifact migration (via gemara-mcp) |
| `/workbench/publish` | OCI artifact publish (via oras-mcp) |
| `/workbench/registry/*` | OCI registry browse (via oras-mcp) |

### Studio Assistant (LangGraph)

Graph topology:

```
__start__ -> router -> (posture_check | audit_production | clarify)

Audit production subgraph:
  agent -> tools -> agent ... -> extract_draft -> validate_draft -> (publish | fix | halt)
  publish has interrupt_before for human approval.

Posture check subgraph:
  agent -> tools -> agent ... -> __end__
```

The assistant uses MCP tools to:
- Query evidence and posture via `complytime-mcp`
- Validate/migrate Gemara artifacts via `gemara-mcp`
- Browse/publish OCI artifacts via `oras-mcp`
- Read policies, catalogs, requirements via `complytime-mcp`

### MCP Tool Access

MCP servers run as separate pods managed by kagent's KMCP controller. The workbench and assistant connect to them over HTTP.

| MCP Server | Surface | Purpose |
|:--|:--|:--|
| gemara-mcp | Gemara schema validation, artifact migration | Artifact quality |
| oras-mcp | OCI registry operations | Artifact distribution |
| complytime-mcp | Read-only platform data (`complytime://*` URIs) | Evidence, policies, posture queries |

### Checkpointer

LangGraph agent state persists to PostgreSQL using `PostgresSaver` with a `psycopg_pool.ConnectionPool`. The `setup()` call uses `autocommit=True` to avoid transaction conflicts with `CREATE INDEX CONCURRENTLY`.

## Data Ownership

The workbench does **not** own platform data. It reads from the gateway API (via complytime-mcp or direct REST) and writes audit results back via `POST /api/draft-audit-logs`. Chat state and agent checkpoints are workbench-owned data stored in the same PostgreSQL instance under separate tables.

## Deployment

Deployed as a Kubernetes Deployment (`studio-workbench`) via the Helm chart in [studio-deploy](https://github.com/complytime-labs/studio-deploy). The assistant runs as a separate kagent BYO Agent CRD (`studio-assistant`).

## Related Docs

| Doc | Topic |
|:--|:--|
| [ADRs](decisions/) | Agent and workbench decisions |
| [complytime-core architecture](https://github.com/complytime-labs/complytime-core/blob/main/docs/architecture.md) | Data platform API |
