# Contributing

See the [ComplyTime organization contribution guidelines](https://github.com/complytime/org-infra/blob/main/CONTRIBUTING.md).

## Issue-Driven Workflow

All work should start with a GitHub issue. Use the issue templates when creating new issues:

| Template | When to Use |
|:--|:--|
| Bug Report | Something is broken or behaving unexpectedly |
| Feature Request | New functionality or enhancement to existing behavior |
| Design Discussion | Architectural questions that need exploration before implementation |
| Epic | Grouping related issues under a theme |

**Routing:**
- **Clear problem, clear solution** → Feature Request or Bug Report → implement
- **Multiple valid approaches or upstream dependency** → Design Discussion → explore → optionally graduate to an [ADR](docs/decisions/)
- **Mechanical cleanup (CI, tests, docs)** → bundle related items into a single issue with a checklist

## Adding a New Agent

1. Create `agents/<name>/` with `agent.yaml` and `prompt.py`
2. Add a `Dockerfile` that serves A2A at `/.well-known/agent-card.json`
3. Register the agent via a kagent BYO Agent CRD in the platform Helm chart

## Pull Requests

- Branch from `main`
- Follow [Conventional Commits](https://www.conventionalcommits.org/)
- PRs require review from at least two maintainers
- Use the PR template — fill in Summary, Changes, Test Plan, and Related Issues
