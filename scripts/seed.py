"""Deja el entorno de demo en su estado inicial.

- Repo git «remoto» (hace de Azure Repos) con el proyecto de tests de QA en main.
- Azure DevOps simulado con Features, casos automatizados y Test Plans.
- Base de datos del asistente vacía y workspace limpio.

Uso: uv run python scripts/seed.py   (con los servicios parados, o reinícialos después)
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mocks.azure_devops import seed as azure_seed  # noqa: E402
from qa_assistant.adapters.git import git  # noqa: E402
from qa_assistant.config import settings  # noqa: E402

SEED_REPO = ROOT / "sample_data" / "test-repo-seed"


def seed_remote() -> None:
    remote = settings.remote_repo
    shutil.rmtree(remote, ignore_errors=True)
    remote.parent.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "--bare", "-b", "main", str(remote))
    with tempfile.TemporaryDirectory() as tmp:
        wt = Path(tmp) / "wt"
        shutil.copytree(SEED_REPO, wt, ignore=shutil.ignore_patterns("bin", "obj", "TestResults"))
        git("init", "-q", "-b", "main", cwd=wt)
        git("add", "-A", cwd=wt)
        git("-c", "user.name=Equipo QA", "-c", "user.email=qa@example.invalid", "commit", "-q",
            "-m", "Proyecto de tests E2E de la tienda web", cwd=wt)
        git("remote", "add", "origin", str(remote), cwd=wt)
        git("push", "-q", "origin", "main", cwd=wt)


def main() -> None:
    for path in (settings.workspace, settings.results, settings.uploads):
        shutil.rmtree(path, ignore_errors=True)
    db = settings.data_dir / "qa-assistant.db"
    for suffix in ("", "-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    seed_remote()
    azure_seed.seed()
    print(f"Entorno inicializado en {settings.data_dir}")


if __name__ == "__main__":
    main()
