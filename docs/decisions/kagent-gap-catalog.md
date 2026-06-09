# Kagent Declarative Agent Gap Catalog

**Date**: 2026-04-18
**Updated**: 2026-06-09
**Status**: Reference — documents why studio uses BYO LangGraph agents instead of kagent declarative CRDs

## Summary

Nine kagent declarative agent limitations motivated the decision to use BYO LangGraph agents (see [[byo-langgraph-architecture]]). Gaps #1-6 are architectural limitations of the declarative CRD model. They remain open upstream but are **not blocking** because BYO LangGraph bypasses all of them. Gap #7 is fixed upstream as of kagent v0.9.5.

This document is a historical reference explaining the architectural choice, not an active blocker backlog.

## Architectural Gaps (bypassed by BYO LangGraph)

### 1. No MCP resource reading

**Issue**: `KAgentMcpToolset` never sets `use_mcp_resources=True`. Agents cannot access MCP resources like `gemara://lexicon` or `gemara://schema/definitions`.

**Impact**: Agents lack vocabulary and schema context. Knowledge must be hardcoded in skills.

**BYO status**: Not blocking — LangGraph agents configure MCP clients directly.

**Upstream**: [kagent-dev/kagent#890](https://github.com/kagent-dev/kagent/issues/890)

### 2. No structured artifact emission

**Issue**: `event_converter.py` ignores `artifact_delta` on ADK events. The final `TaskArtifactUpdateEvent` mirrors status text, not distinct typed artifacts.

**Impact**: All agent output arrives as chat text. Clients must use regex to extract YAML.

**BYO status**: Not blocking — LangGraph agents use client-side artifact extraction (ADR 0020).

### 3. No `before_agent_callback`

**Issue**: Declarative Agent CRD has no field for pre-processing hooks.

**Impact**: Cannot inject MCP resources, validate inputs, or structure context before the LLM runs.

**BYO status**: Not blocking — LangGraph graph nodes handle pre-processing.

### 4. No `after_agent_callback`

**Issue**: Declarative Agent CRD has no field for post-processing hooks.

**Impact**: Cannot validate output, cross-reference check, or gate artifact emission deterministically.

**BYO status**: Not blocking — LangGraph graph nodes handle post-processing and validation.

### 5. No agent chaining / pipeline support

**Issue**: Each Declarative Agent CRD defines a single agent. No DAG, pipeline, or multi-step flow support.

**Impact**: Multi-step flows require manual human bridging between jobs.

**BYO status**: Not blocking — LangGraph provides native graph topology (router -> subgraphs).

### 6. No `before_tool_callback`

**Issue**: Declarative Agent CRD has no field for tool call interception.

**Impact**: Cannot sanitize queries, rate-limit tool calls, or gate sensitive operations.

**BYO status**: Not blocking — LangGraph tool nodes handle interception.

## Operational Issues

### 7. `allowedHeaders` bug in Go runtime

**Issue**: `allowedHeaders` on MCP server config does not propagate request headers in the Go runtime.

**Status**: **Fixed upstream** (kagent v0.9.5). No longer relevant.

### 8. No per-session MCP resource caching

**Issue**: Each tool call creates a fresh context. No mechanism to cache expensive resource loads across turns.

**Impact**: Repeated schema/lexicon fetches waste tokens and add latency.

**BYO status**: Not blocking — LangGraph agents can share MCP client instances across graph execution.

### 9. `gemara-mcp` thread leak (shared deployment)

**Issue**: `gemara-mcp` Go binary leaks OS threads under shared deployment.

**BYO status**: Not blocking — BYO agent uses sidecar model to isolate MCP processes.
