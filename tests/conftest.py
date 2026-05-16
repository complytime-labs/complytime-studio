# SPDX-License-Identifier: Apache-2.0

import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def workbench_client() -> httpx.AsyncClient:
    """Async test client for the workbench Starlette app (ASGI transport)."""
    from workbench.app import create_app

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")
