# Contributing

See the [ComplyTime organization contribution guidelines](https://github.com/complytime/org-infra/blob/main/CONTRIBUTING.md).

## Adding a New Agent

Follow the JTBD framework in [AGENTS.md](https://github.com/complytime/complytime-studio/blob/main/AGENTS.md):

1. Create `agents/<name>/` with `agent.yaml` and `prompt.md`
2. Add a `Dockerfile` that serves A2A at `/.well-known/agent-card.json`
3. Register the agent CRD template in the platform Helm chart

## Pull Requests

- Branch from `main`
- Follow [Conventional Commits](https://www.conventionalcommits.org/)
- PRs require review from at least two maintainers
