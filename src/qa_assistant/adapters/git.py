"""Operaciones git mínimas por subprocess (sin dependencias extra)."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

AUTHOR = ["-c", "user.name=Asistente QA", "-c", "user.email=qa-assistant@example.invalid"]


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: Path | None = None, git_dir: Path | None = None, check: bool = True) -> str:
    cmd = ["git", *AUTHOR]
    if git_dir is not None:
        cmd += ["--git-dir", str(git_dir)]
    cmd += list(args)
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and res.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {res.stderr.strip() or res.stdout.strip()}")
    return res.stdout


def branch_exists(remote: Path, branch: str) -> bool:
    return bool(git("branch", "--list", branch, git_dir=remote).strip())


def diff(remote: Path, branch: str, target: str = "main") -> str:
    """Diff de la rama frente al punto en que se separó del destino (como una PR)."""
    return git("diff", f"{target}...{branch}", git_dir=remote)


def changed_files(remote: Path, branch: str, target: str = "main") -> list[str]:
    out = git("diff", "--name-only", f"{target}...{branch}", git_dir=remote)
    return [line for line in out.splitlines() if line]


def head(remote: Path, ref: str) -> str:
    return git("rev-parse", ref, git_dir=remote).strip()


def merge_into(remote: Path, branch: str, message: str, target: str = "main") -> str:
    """Hace merge --no-ff de una rama en el destino de un repo bare (como al completar una PR)."""
    tmp = Path(tempfile.mkdtemp(prefix="merge-"))
    try:
        git("clone", "-q", "--branch", target, str(remote), str(tmp / "wt"))
        wt = tmp / "wt"
        git("fetch", "-q", "origin", branch, cwd=wt)
        git("merge", "--no-ff", "-m", message, "FETCH_HEAD", cwd=wt)
        git("push", "-q", "origin", target, cwd=wt)
        return git("rev-parse", "HEAD", cwd=wt).strip()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def show(remote: Path, ref: str, path: str) -> str | None:
    res = subprocess.run(["git", "--git-dir", str(remote), "show", f"{ref}:{path}"], capture_output=True, text=True)
    return res.stdout if res.returncode == 0 else None
