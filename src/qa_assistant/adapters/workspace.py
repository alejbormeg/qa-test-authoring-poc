"""Copia de trabajo del repositorio de tests de QA.

La base de datos es la fuente de verdad del código generado; el workspace se reconstruye desde
origin/main + los ficheros de la ejecución cada vez que hace falta compilar, ejecutar o publicar.
"""

from __future__ import annotations

import json
import re
import threading
import unicodedata
from pathlib import Path

from ..config import settings
from .git import git

LOCK = threading.RLock()  # un único workspace compartido: las operaciones se serializan
GENERATED_DIR = "Tests/Generated"
GENERATED_NS = f"{settings.test_namespace}.Generated"

USINGS = """using System.Text.RegularExpressions;
using Microsoft.Playwright;
using QaWeb.Tests.Pages;
using QaWeb.Tests.Support;
using static QaWeb.Tests.Support.Components;
"""


def ascii_fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def pascal(text: str, max_len: int = 60) -> str:
    words = re.findall(r"[A-Za-z0-9]+", ascii_fold(text))
    out = "".join(w[:1].upper() + w[1:] for w in words)
    return out[:max_len] or "Caso"


def method_name(ext_id: str, title: str) -> str:
    return f"{re.sub(r'[^A-Za-z0-9]+', '_', ascii_fold(ext_id)).strip('_').upper()}_{pascal(title)}"


def class_name(feature_title: str) -> str:
    return f"{pascal(feature_title, 40)}Tests"


def test_file(cls: str, ext_id: str) -> str:
    return f"{GENERATED_DIR}/{cls.removesuffix('Tests')}/{re.sub(r'[^A-Za-z0-9]+', '_', ext_id).upper()}.cs"


def render_test_file(cls: str, method: str, feature_id: int, ext_id: str, title: str, body: str) -> str:
    """Cada caso va en su propio fichero (clase parcial): diffs y revisiones por caso."""
    indented = "\n".join(("        " + line) if line.strip() else "" for line in body.strip("\n").splitlines())
    return (f"{USINGS}\nnamespace {GENERATED_NS};\n\n"
            f"// Generado por el asistente de QA a partir del caso {ext_id} y revisado por QA antes del merge.\n"
            f"public partial class {cls} : BaseTest\n{{\n"
            f"    /// <summary>{ext_id} · {title.replace('<', '&lt;').replace('>', '&gt;')}</summary>\n"
            f"    [Fact]\n    [Trait(\"Feature\", \"{feature_id}\")]\n    [Trait(\"Caso\", \"{ext_id}\")]\n"
            f"    public async Task {method}()\n    {{\n{indented}\n    }}\n}}\n")


def fqn(cls: str, method: str) -> str:
    return f"{GENERATED_NS}.{cls}.{method}"


# ---------------------------------------------------------------- mapeos

def format_mapping(mapping: dict[str, dict[str, str]]) -> str:
    """Mismo formato que los ficheros del equipo: una entrada por línea (diffs mínimos)."""
    lines = []
    for key, entry in mapping.items():
        inner = ", ".join(f"{json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}" for k, v in entry.items())
        lines.append(f"  {json.dumps(key, ensure_ascii=False)}: {{ {inner} }}")
    return "{\n" + ",\n".join(lines) + "\n}\n"


class Workspace:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.workspace

    def path(self, rel: str) -> Path:
        p = (self.root / rel).resolve()
        if not str(p).startswith(str(self.root.resolve())):
            raise PermissionError(f"Ruta fuera del repositorio: {rel}")
        return p

    def prepare(self, branch: str) -> None:
        """Deja el workspace en origin/main sobre la rama de la ejecución (conserva bin/obj)."""
        if not (self.root / ".git").exists():
            self.root.parent.mkdir(parents=True, exist_ok=True)
            git("clone", "-q", str(settings.remote_repo), str(self.root))
        git("fetch", "-q", "--prune", "origin", cwd=self.root)
        git("checkout", "-q", "-f", "-B", branch, "origin/main", cwd=self.root)
        git("clean", "-q", "-fdx", "-e", "bin", "-e", "obj", cwd=self.root)

    # lectura
    def read(self, rel: str) -> str:
        return self.path(rel).read_text(encoding="utf-8")

    def list(self, pattern: str) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.glob(pattern) if p.is_file())

    def routes(self) -> dict[str, str]:
        return json.loads(self.read("Mappings/_rutas.json"))

    def mapping(self, page: str) -> dict[str, dict[str, str]]:
        p = self.path(f"Mappings/{page}.json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def mappings(self) -> dict[str, dict[str, dict[str, str]]]:
        return {Path(f).stem: self.mapping(Path(f).stem) for f in self.list("Mappings/*.json")
                if not Path(f).stem.startswith("_")}

    # escritura
    def write(self, rel: str, content: str) -> None:
        p = self.path(rel)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def add_components(self, components: list[dict]) -> None:
        by_page: dict[str, list[dict]] = {}
        for c in components:
            by_page.setdefault(c["pagina"], []).append(c)
        for page, comps in by_page.items():
            mapping = self.mapping(page)
            for c in comps:
                mapping.setdefault(c["nombre"], {"selector": c["selector"], "tipo": c["tipo"],
                                                 "descripcion": c["descripcion"]})
            self.write(f"Mappings/{page}.json", format_mapping(mapping))

    def commit_and_push(self, branch: str, message: str) -> str:
        git("add", "-A", cwd=self.root)
        git("-c", "user.name=Asistente QA", "-c", "user.email=qa-assistant@example.invalid",
            "commit", "-q", "-m", message, cwd=self.root)
        git("push", "-q", "-f", "origin", f"{branch}:{branch}", cwd=self.root)
        return git("rev-parse", "HEAD", cwd=self.root).strip()
