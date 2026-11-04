"""Compilación y ejecución de los tests C# (xUnit + Playwright) con `dotnet`, leyendo el TRX."""

from __future__ import annotations

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ..config import settings

NS = {"t": "http://microsoft.com/schemas/VisualStudio/TeamTest/2010"}
ENV = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "DOTNET_NOLOGO": "1", "DOTNET_CLI_UI_LANGUAGE": "es",
       "MSBUILDDISABLENODEREUSE": "1"}


@dataclass
class BuildResult:
    ok: bool
    errors: list[str]
    output: str


@dataclass
class TestResult:
    name: str
    outcome: str          # Passed | Failed | NotExecuted
    duration_ms: int
    message: str


def build(root: Path) -> BuildResult:
    res = subprocess.run([settings.dotnet, "build", "-nologo", "-v", "q", "-clp:NoSummary"], cwd=root,
                         capture_output=True, text=True, env=ENV, timeout=600)
    out = res.stdout + res.stderr
    errors = sorted({_short(line, root) for line in out.splitlines() if re.search(r"\berror [A-Z]+\d+", line)})
    return BuildResult(res.returncode == 0, errors, out)


def errors_for(build_result: BuildResult, rel_file: str) -> list[str]:
    return [e for e in build_result.errors if e.startswith(rel_file)]


def _short(line: str, root: Path) -> str:
    line = line.replace(str(root) + "/", "")
    return re.sub(r"\s*\[[^\]]+\.csproj\]$", "", line).strip()


def run_tests(root: Path, fqns: list[str], results_dir: Path) -> list[TestResult]:
    results_dir.mkdir(parents=True, exist_ok=True)
    trx = results_dir / "resultados.trx"
    trx.unlink(missing_ok=True)
    flt = "|".join(f"FullyQualifiedName={n}" for n in fqns)
    env = {**ENV, "BASE_URL": settings.demo_site_url}
    subprocess.run([settings.dotnet, "test", "--no-build", "--nologo", "--settings", ".runsettings",
                    "--filter", flt, "--logger", f"trx;LogFileName={trx.name}", "--results-directory",
                    str(results_dir)],
                   cwd=root, capture_output=True, text=True, env=env, timeout=900)
    return parse_trx(trx) if trx.exists() else []


def parse_trx(path: Path) -> list[TestResult]:
    tree = ET.parse(path)
    out = []
    for r in tree.getroot().iterfind(".//t:UnitTestResult", NS):
        msg_el = r.find("t:Output/t:ErrorInfo/t:Message", NS)
        stack_el = r.find("t:Output/t:ErrorInfo/t:StackTrace", NS)
        message = (msg_el.text or "").strip() if msg_el is not None else ""
        if stack_el is not None and stack_el.text:
            frames = [ln.strip() for ln in stack_el.text.splitlines() if "Tests/Generated" in ln or "Generated." in ln]
            if frames:
                message += "\n" + "\n".join(re.sub(r" in \S*/(Tests/Generated/)", r" in \1", f) for f in frames[:3])
        h, m, s = r.get("duration", "0:0:0").split(":")
        out.append(TestResult(r.get("testName", ""), r.get("outcome", ""),
                              int((int(h) * 3600 + int(m) * 60 + float(s)) * 1000), message))
    return out
