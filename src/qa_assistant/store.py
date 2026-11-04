"""Persistencia (SQLite) y utilidades de acceso para el servicio y la UI."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select

from .config import settings
from .domain.models import CaseDraft, Decision, LogEntry, Run, Setting, utcnow

engine = create_engine(settings.db_url, connect_args={"check_same_thread": False, "timeout": 30})


@event.listens_for(engine, "connect")
def _sqlite_pragmas(conn, _record) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.close()


SQLModel.metadata.create_all(engine)
_write_lock = threading.RLock()

DEFAULTS = {"baseline_minutes_per_case": "45", "hourly_cost_eur": "35"}


@contextmanager
def session() -> Iterator[Session]:
    with _write_lock, Session(engine, expire_on_commit=False) as s:
        yield s


def get_run(run_id: int) -> Run | None:
    with session() as s:
        return s.get(Run, run_id)


def runs() -> list[Run]:
    with session() as s:
        return list(s.exec(select(Run).order_by(Run.id.desc())))


def cases(run_id: int) -> list[CaseDraft]:
    with session() as s:
        return list(s.exec(select(CaseDraft).where(CaseDraft.run_id == run_id).order_by(CaseDraft.position)))


def all_cases() -> list[CaseDraft]:
    with session() as s:
        return list(s.exec(select(CaseDraft)))


def get_case(case_id: int) -> CaseDraft | None:
    with session() as s:
        return s.get(CaseDraft, case_id)


def update_run(run_id: int, **fields: Any) -> Run:
    with session() as s:
        run = s.get(Run, run_id)
        for k, v in fields.items():
            setattr(run, k, v)
        run.version += 1
        s.add(run)
        s.commit()
        s.refresh(run)
        return run


def touch(run_id: int) -> None:
    update_run(run_id)


def update_case(case_id: int, **fields: Any) -> CaseDraft:
    with session() as s:
        case = s.get(CaseDraft, case_id)
        for k, v in fields.items():
            setattr(case, k, v)
        s.add(case)
        run = s.get(Run, case.run_id)
        run.version += 1
        s.add(run)
        s.commit()
        s.refresh(case)
        return case


def add(obj: Any) -> Any:
    with session() as s:
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj


def log(run_id: int, text: str, level: str = "info") -> None:
    with session() as s:
        s.add(LogEntry(run_id=run_id, text=text, level=level))
        run = s.get(Run, run_id)
        if run:
            run.version += 1
            s.add(run)
        s.commit()


def logs(run_id: int, limit: int = 400) -> list[LogEntry]:
    with session() as s:
        q = select(LogEntry).where(LogEntry.run_id == run_id).order_by(LogEntry.id.desc()).limit(limit)
        return list(reversed(list(s.exec(q))))


def decide(run_id: int, user: str, action: str, detail: str = "") -> None:
    with session() as s:
        s.add(Decision(run_id=run_id, user=user, action=action, detail=detail))
        s.commit()
    log(run_id, f"👤 {user}: {action}{' · ' + detail if detail else ''}", "human")


def decisions(run_id: int | None = None) -> list[Decision]:
    with session() as s:
        q = select(Decision).order_by(Decision.id.desc())
        if run_id is not None:
            q = q.where(Decision.run_id == run_id)
        return list(s.exec(q))


def mark(run_id: int, phase: str, edge: str) -> None:
    """Marca inicio/fin de una fase (para el dashboard)."""
    with session() as s:
        run = s.get(Run, run_id)
        timings = dict(run.timings or {})
        entry = dict(timings.get(phase, {}))
        entry[edge] = utcnow().isoformat()
        timings[phase] = entry
        run.timings = timings
        run.version += 1
        s.add(run)
        s.commit()


def add_usage(run_id: int, usage: dict[str, float]) -> None:
    if not usage:
        return
    with session() as s:
        run = s.get(Run, run_id)
        total = dict(run.usage or {})
        for k, v in usage.items():
            total[k] = round(total.get(k, 0) + v, 6)
        run.usage = total
        run.version += 1
        s.add(run)
        s.commit()


def get_setting(key: str) -> str:
    with session() as s:
        row = s.get(Setting, key)
        return row.value if row else DEFAULTS.get(key, "")


def set_setting(key: str, value: str) -> None:
    with session() as s:
        row = s.get(Setting, key) or Setting(key=key, value=value)
        row.value = value
        s.add(row)
        s.commit()


def now_iso() -> str:
    return utcnow().isoformat()
