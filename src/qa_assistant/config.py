"""Configuración central, leída de variables de entorno (con .env opcional en la raíz)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


_load_dotenv()


def _dotnet() -> str:
    if os.environ.get("DOTNET"):
        return os.environ["DOTNET"]
    local = Path.home() / ".dotnet" / "dotnet"
    if local.exists():
        return str(local)
    return shutil.which("dotnet") or "dotnet"


def _ai_mode() -> str:
    mode = os.environ.get("QA_AI", "auto").lower()
    if mode == "auto":
        return "claude" if os.environ.get("ANTHROPIC_API_KEY") else "mock"
    return mode


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("QA_DATA_DIR", ROOT / ".data")))
    app_port: int = int(os.environ.get("QA_APP_PORT", "8600"))
    azure_port: int = int(os.environ.get("QA_AZURE_PORT", "8601"))
    demo_site_port: int = int(os.environ.get("QA_DEMO_SITE_PORT", "8602"))

    azure_org: str = os.environ.get("AZURE_ORG", "demo-org")
    azure_project: str = os.environ.get("AZURE_PROJECT", "QA-Web")
    azure_repo: str = os.environ.get("AZURE_REPO", "qa-web-tests")
    azure_pat: str = os.environ.get("AZURE_PAT", "pat-demo-poc")
    azure_base_url: str = os.environ.get("AZURE_BASE_URL", "")

    dotnet: str = field(default_factory=_dotnet)
    ai_mode: str = field(default_factory=_ai_mode)
    claude_model: str = os.environ.get("QA_CLAUDE_MODEL", "claude-opus-5-5")
    claude_fallbacks: bool = os.environ.get("QA_CLAUDE_FALLBACKS", "1") == "1"
    max_fix_attempts: int = int(os.environ.get("QA_MAX_FIX_ATTEMPTS", "2"))

    test_assembly: str = "QaWeb.Tests.dll"
    test_namespace: str = "QaWeb.Tests"

    @property
    def azure_url(self) -> str:
        base = self.azure_base_url or f"http://127.0.0.1:{self.azure_port}"
        return f"{base.rstrip('/')}/{self.azure_org}/{self.azure_project}"

    @property
    def azure_console_url(self) -> str:
        return f"http://localhost:{self.azure_port}/console"

    @property
    def demo_site_url(self) -> str:
        return os.environ.get("DEMO_SITE_URL", f"http://localhost:{self.demo_site_port}")

    @property
    def remote_repo(self) -> Path:
        return self.data_dir / "remotes" / f"{self.azure_repo}.git"

    @property
    def workspace(self) -> Path:
        return self.data_dir / "workspace" / self.azure_repo

    @property
    def uploads(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def results(self) -> Path:
        return self.data_dir / "results"

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'qa-assistant.db'}"

    @property
    def azure_state_file(self) -> Path:
        return self.data_dir / "azure-mock.json"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
