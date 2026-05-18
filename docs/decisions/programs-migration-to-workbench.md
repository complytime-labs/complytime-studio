# 0036 — Programs Migration to Workbench

**Status:** Accepted
**Date:** 2026-05-16

## Context

The gateway (`complytime-core`) contains a full Programs CRUD implementation: `ProgramStore` interface, `handlers_programs.go`, `internal/postgres/programs.go`, and associated DB migrations. However, `main.go` sets `Programs: nil`, so the routes are never registered. Programs were always disabled in the current architecture.

ADR #0025 (Data Platform + Workbench Split) established that `complytime-core` is a pure data platform — evidence storage, certifier pipeline, posture, content ingestion. Programs are compliance management workflow state: timelines, team assignments, framework bindings, threshold configuration. This is presentation/workflow logic, not data platform logic.

The serving-layer ADR (#0031) listed `programs` as a core MCP resource. This was incorrect and must be corrected.

## Decision

Move Programs to `complytime-studio` (the workbench).

### What moves

| Artifact | From | To |
|:--|:--|:--|
| `ProgramStore` interface | `internal/store/store.go` | `complytime-studio` models |
| `handlers_programs.go` | `internal/store/` | `complytime-studio` Starlette routes |
| `programs.go` (Postgres impl) | `internal/postgres/` | `complytime-studio` data layer |
| Programs DB tables | `public` schema | `workbench` schema (same DB instance) |
| Programs CRUD tests | `complytime-core` | `complytime-studio` |

### Schema separation

All program-related tables live in the `workbench` Postgres schema within the shared `studio` database:

| Table | Schema | Owner |
|:--|:--|:--|
| `programs` | `workbench` | complytime-studio |
| `jobs` | `workbench` | complytime-studio |
| `program_members` | `workbench` | complytime-studio |
| `program_findings` | `workbench` | complytime-studio |
| `recommendation_dismissals` | `workbench` | complytime-studio |

The workbench runs its own migration system (`workbench/migrations/*.sql`) tracked in `workbench.schema_migrations`. Core migration 015 handles moving existing tables from `public` to `workbench` for upgrades. Cross-schema reads (e.g., `public.mapping_documents` for guidance catalog resolution) use explicit schema-qualified names.

### API surface

Programs CRUD lives under the workbench path:

```
GET    /workbench/programs
POST   /workbench/programs
GET    /workbench/programs/{id}
PUT    /workbench/programs/{id}
DELETE /workbench/programs/{id}
```

The UI already routes `/workbench/*` to the workbench via Nginx. No gateway routing changes needed.

### MCP surface

> **Update:** `complytime-mcp` and `studio-mcp` were removed entirely (ADR 0041). Programs data is accessed via workbench REST endpoints. No MCP surface changes needed.

~~- `complytime-mcp` (core): remove `programs` and `programs/{id}` resources.~~
~~- `studio-mcp` (workbench): add `programs` and `programs/{id}` resources.~~

### NATS integration

The workbench subscribes to `core.events.*` for evidence arrival and posture changes. Programs can use these events to update program health status based on policy coverage and posture data.

## Consequences

- Gateway has zero program awareness. No `ProgramStore`, no handlers, no DB tables.
- Programs can reference core policies by ID without owning them.
- The workbench owns all cross-record, calculated state: program health, coverage percentages, readiness.
- `test-headless.sh` already skips Programs CRUD on 404 (implemented in this change set).
- Studio UI programs view calls `/workbench/programs` instead of `/api/programs`.
- The `workbench` schema provides a clean boundary — `studio_reader` has `SELECT` access for dashboards; core never queries these tables.

## Migration Steps

1. Implement Programs model + routes in `complytime-studio`
2. Create `workbench.programs` table migration
3. ~~Update `studio-mcp` with programs resources~~ (superseded by ADR 0041)
4. Update `studio-ui` to call `/workbench/programs`
5. Remove Programs code from `complytime-core` (dead code cleanup)
6. ~~Update serving-layer ADR (#0031) to remove programs from core MCP~~ (superseded by ADR 0041)
