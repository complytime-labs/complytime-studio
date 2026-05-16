# Kagent Declarative Agent Gap Catalog

**Date**: 2026-04-18
**Status**: Active — tracks upstream kagent limitations that motivated the BYO ADK agent

## Summary

Nine kagent declarative agent limitations block end-to-end artifact authoring flows. Six are architectural (missing features), three are operational (bugs/instability). The BYO ADK agent bypasses all architectural gaps.

## Architectural Gaps

### 1. No MCP resource reading

**Issue**: `KAgentMcpToolset` never sets `use_mcp_resources=True`. Agents cannot access MCP resources like `gemara://lexicon` or `gemara://schema/definitions`.

**Impact**: Agents lack vocabulary and schema context. Knowledge must be hardcoded in skills.

**ADK capability**: `McpToolset(use_mcp_resources=True)` injects `load_mcp_resource` tool.

**Fix complexity**: Easy — config passthrough in `KAgentMcpToolset` + CRD schema addition.

**Upstream**: [kagent-dev/kagent#890](https://github.com/kagent-dev/kagent/issues/890)

### 2. No structured artifact emission

**Issue**: `event_converter.py` ignores `artifact_delta` on ADK events. The final `TaskArtifactUpdateEvent` mirrors status text, not distinct typed artifacts.

**Impact**: All agent output arrives as chat text. Clients must use regex to extract YAML.

**ADK capability**: `save_artifact` records `artifact_delta` on `EventActions`.

**Fix complexity**: Medium — custom event converter (~50 lines) + artifact service loading.

**Upstream**: No issue filed yet. Template below.

### 3. No `before_agent_callback`

**Issue**: Declarative Agent CRD has no field for pre-processing hooks.

**Impact**: Cannot inject MCP resources, validate inputs, or structure context before the LLM runs. Every interaction starts cold.

**ADK capability**: `LlmAgent(before_agent_callback=...)` fully supported.

**Fix complexity**: Medium — CRD schema addition + executor wiring.

### 4. No `after_agent_callback`

**Issue**: Declarative Agent CRD has no field for post-processing hooks.

**Impact**: Cannot validate output, cross-reference check, or gate artifact emission deterministically. The LLM decides whether to validate.

**ADK capability**: `LlmAgent(after_agent_callback=...)` fully supported.

**Fix complexity**: Medium — same as #3.

### 5. No agent chaining / pipeline support

**Issue**: Each Declarative Agent CRD defines a single agent. No DAG, pipeline, or multi-step flow support.

**Impact**: Multi-step flows (threat → control → risk → policy) require manual human bridging between jobs.

**ADK capability**: Sub-agents and sequential agents supported in code.

**Fix complexity**: Hard — requires orchestration model design.

### 6. No `before_tool_callback`

**Issue**: Declarative Agent CRD has no field for tool call interception.

**Impact**: Cannot sanitize ClickHouse SQL queries (SQL injection risk), rate-limit tool calls, or gate sensitive operations.

**ADK capability**: `LlmAgent(before_tool_callback=...)` fully supported.

**Fix complexity**: Medium — same pattern as #3/#4.

## Operational Issues

### 7. `allowedHeaders` bug in Go runtime

**Issue**: `allowedHeaders` on MCP server config does not propagate request headers in the Go runtime. Works in Python runtime.

**Impact**: GitHub MCP requires a static PAT even when OBO should suffice.

**Status**: Workaround in place (Python runtime + static token fallback).

### 8. No per-session MCP resource caching

**Issue**: Each tool call creates a fresh context. No mechanism to cache expensive resource loads across turns.

**Impact**: Repeated schema/lexicon fetches waste tokens and add latency.

**Fix complexity**: Medium — session-scoped cache in executor.

### 9. `gemara-mcp` thread leak (shared deployment)

**Issue**: `gemara-mcp` Go binary leaks OS threads, leading to `newosproc` errors after ~24h.

**Impact**: Shared MCP deployment crashes under load.

**Status**: Documented in `docs/decisions/gemara-mcp-session-failures.md`. BYO agent uses sidecar model to isolate.

## Upstream Issue Template

```markdown
### Feature: [Title]

**Problem**: [One-line description of what's missing]

**ADK support**: [Which ADK API already supports this]

**Proposed change**:
1. [CRD schema addition]
2. [Executor wiring]
3. [Test coverage]

**Reference implementation**: https://github.com/complytime-labs/complytime-core/tree/main/agents/gap-analyst
```
