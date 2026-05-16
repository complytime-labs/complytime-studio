# Architecture Decision Records

Decisions specific to the Studio Workbench (LangGraph agent, A2A protocol, MCP tools).
Cross-cutting platform decisions live in [complytime-core](https://github.com/complytime-labs/complytime-core/tree/main/docs/decisions).

## Active

| # | Decision | Status | Date |
|:--|:--|:--|:--|
| 0005 | [Agent Interaction Model — HITL Chatbot](agent-interaction-model.md) | Accepted | 2026-04-22 |
| 0020 | [Agent Artifact Delivery](agent-artifact-delivery.md) | Phase 1 implemented; Phase 2 deferred | 2026-04-18 |
| 0029 | [Notifications Belong Outside the Gateway](notifications-outside-gateway.md) | Accepted | 2026-05-14 |
| 0030 | [Recommendation Engine Deferred to Workbench](recommendation-engine-deferred.md) | Deferred | 2026-05-14 |
| 0036 | [Programs Migration to Workbench](programs-migration-to-workbench.md) | Accepted | 2026-05-16 |

## Historical / Obsolete

| # | Decision | Status | Date |
|:--|:--|:--|:--|
| 0017 | [Kagent Declarative Agent Gap Catalog](kagent-gap-catalog.md) | Obsolete — agents run in workbench, not kagent | 2026-04-18 |
| 0019 | [ADK Empty Messages Workaround](adk-empty-messages-workaround.md) | Obsolete — replaced by LangGraph | 2026-04-19 |

## Superseded / Resolved

| Decision | Status |
|:--|:--|
| [ADK A2A Streaming](adk-a2a-streaming.md) | Resolved |
| [Agent Trust Model](trust-model-deferred.md) | Rejected for v1 |
