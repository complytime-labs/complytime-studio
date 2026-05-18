# SPDX-License-Identifier: Apache-2.0

ASSISTANT_IMAGE ?= studio-assistant
ASSISTANT_TAG ?= local
CONTAINER_RUNTIME ?= $(shell command -v podman >/dev/null 2>&1 && echo podman || echo docker)

.PHONY: sync-skills image test test-integration lint clean

sync-skills:
	@rsync -a --delete --exclude='.gitkeep' skills/ agents/assistant/skills/

image: sync-skills
	$(CONTAINER_RUNTIME) build --no-cache \
		-f agents/assistant/Dockerfile \
		-t $(ASSISTANT_IMAGE):$(ASSISTANT_TAG) \
		agents/assistant/

test:
	cd agents/assistant && python -m pytest -v
	python -m pytest tests/ -v --ignore=tests/test_a2a_contract.py

test-integration: ## Run A2A contract tests against a live agent (AGENT_URL required)
	AGENT_URL=$${AGENT_URL:-http://localhost:8080} python -m pytest tests/test_a2a_contract.py -v

lint:
	cd agents/assistant && python -m mypy --ignore-missing-imports .

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
