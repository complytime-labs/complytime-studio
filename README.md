# ComplyTime Agents + Studio Workbench

AI agents and the Studio Workbench HTTP server for ComplyTime Studio.

## Components

| Component | Purpose |
|:--|:--|
| **Studio Workbench** (`workbench/`) | Python HTTP server (Starlette) serving `/workbench/*` — A2A routing, agent directory, chat state, Gemara validate/migrate, OCI publish/browse |
| **studio-assistant** (`agents/assistant/`) | LangGraph agent for audit preparation, evidence synthesis, cross-framework coverage analysis |

## Quick Start

```bash
make sync-skills    # Copy shared skills into agent directories
make image          # Build studio-assistant:local
make test           # Run pytest
```

## Structure

```
workbench/            # Studio Workbench HTTP server
  app.py              # Starlette routes: /workbench/*

agents/
  assistant/          # studio-assistant agent
    agent.yaml        # Canonical spec (name, skills, mcp, a2a)
    prompt.md         # Workflow instructions
    main.py           # ADK entrypoint
    Dockerfile        # Container image
    requirements.txt  # Python dependencies
    prompts/          # Few-shot examples
    skills/           # Vendored skills (synced from skills/)

skills/               # Shared knowledge packs
  studio-audit/       # Classification criteria, coverage mapping
  posture-check/      # Pre-audit readiness checks
```

## Workbench API

The workbench serves agent-support endpoints behind Nginx at `/workbench/*`:

| Endpoint | Method | Purpose |
|:--|:--|:--|
| `/workbench/agents` | GET | Agent directory |
| `/workbench/a2a/{name}` | POST | A2A proxy to agents |
| `/workbench/chat/history` | GET/PUT | Conversation state |
| `/workbench/validate` | POST | Gemara artifact validation (MCP) |
| `/workbench/migrate` | POST | Gemara artifact migration (MCP) |
| `/workbench/publish` | POST | OCI bundle publish (MCP) |
| `/workbench/registry/*` | GET | OCI registry browse (MCP) |

## Skills

Skills are reusable knowledge packs injected into agent context at runtime. Shared skills live in `skills/` at the repo root. Each agent vendors a copy under `agents/<name>/skills/` (synced by `make sync-skills`).

## Deployment

The workbench and agents are deployed via the Helm chart in [complytime-studio](https://github.com/complytime/complytime-studio). The Studio UI Nginx routes `/workbench/*` to this service.

Published as `ghcr.io/complytime/studio-assistant:<tag>`.
