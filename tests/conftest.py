"""Entorno aislado para los tests: datos en un directorio temporal y Azure DevOps simulado en un puerto libre."""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from pathlib import Path

import pytest


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_TMP = Path(tempfile.mkdtemp(prefix="qa-poc-tests-"))
os.environ["QA_DATA_DIR"] = str(_TMP)
os.environ["QA_AZURE_PORT"] = str(_free_port())
os.environ["QA_AI"] = "mock"
os.environ.pop("AZURE_BASE_URL", None)


@pytest.fixture(scope="session")
def azure_mock():
    import httpx
    import uvicorn

    from mocks.azure_devops import seed
    from mocks.azure_devops.app import app
    from qa_assistant.config import settings
    from scripts.seed import seed_remote

    seed_remote()
    seed.seed()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=settings.azure_port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            if httpx.get(f"http://127.0.0.1:{settings.azure_port}/_mock/health").status_code == 200:
                break
        except httpx.TransportError:
            time.sleep(0.1)
    yield settings
    server.should_exit = True


@pytest.fixture()
def fresh_azure(azure_mock):
    from mocks.azure_devops import seed

    seed.seed()
    return azure_mock
