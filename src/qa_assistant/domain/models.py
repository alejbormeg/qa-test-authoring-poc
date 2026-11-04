"""Modelo de dominio persistido: ejecuciones, casos, decisiones humanas y log."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


class RunState(StrEnum):
    EXTRAYENDO = "extrayendo"
    EXTRAIDO = "extraido"            # Gate 1 pendiente: QA revisa los casos
    GENERANDO = "generando"
    EN_REVISION = "en_revision"      # Gate 2 pendiente: QA revisa código y resultados
    PR_ABIERTA = "pr_abierta"
    MERGEADO = "mergeado"            # Gate 3 pendiente: QA confirma el registro en Azure
    REGISTRANDO = "registrando"
    REGISTRADO = "registrado"
    ERROR = "error"
    DESCARTADO = "descartado"


STATE_LABELS = {
    RunState.EXTRAYENDO: "Extrayendo casos",
    RunState.EXTRAIDO: "Revisión de casos",
    RunState.GENERANDO: "Generando tests",
    RunState.EN_REVISION: "Revisión del código",
    RunState.PR_ABIERTA: "Pull request abierta",
    RunState.MERGEADO: "Confirmar registro",
    RunState.REGISTRANDO: "Registrando en Azure",
    RunState.REGISTRADO: "Registrado",
    RunState.ERROR: "Error",
    RunState.DESCARTADO: "Descartado",
}

STATE_COLORS = {
    RunState.EXTRAYENDO: "blue-grey", RunState.EXTRAIDO: "amber-8", RunState.GENERANDO: "blue-grey",
    RunState.EN_REVISION: "amber-8", RunState.PR_ABIERTA: "indigo", RunState.MERGEADO: "amber-8",
    RunState.REGISTRANDO: "blue-grey", RunState.REGISTRADO: "positive", RunState.ERROR: "negative",
    RunState.DESCARTADO: "grey",
}

# Estados que esperan una decisión humana
WAITING_HUMAN = {RunState.EXTRAIDO, RunState.EN_REVISION, RunState.PR_ABIERTA, RunState.MERGEADO}


class CaseStatus(StrEnum):
    PENDIENTE = "pendiente"
    APROBADO = "aprobado"
    DESCARTADO = "descartado"


class Run(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=utcnow)
    created_by: str
    dff_name: str
    dff_path: str
    ai_mode: str
    state: str = RunState.EXTRAYENDO
    feature_id: int
    feature_title: str
    plan_id: int
    plan_name: str
    suite_id: int | None = None
    suite_name: str
    test_class: str = ""
    branch: str = ""
    pr_id: int | None = None
    pr_status: str = ""
    pr_votes: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    error: str | None = None
    failed_phase: str | None = None
    busy: str | None = None
    version: int = 0
    timings: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    usage: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    new_components: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    notes: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    dff_meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class CaseDraft(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    position: int = 0
    ext_id: str
    title: str
    preconditions: str = ""
    steps: list[dict[str, str]] = Field(default_factory=list, sa_column=Column(JSON))
    data: str = ""
    expected: str = ""
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    duplicate_of: int | None = None
    status: str = CaseStatus.PENDIENTE
    edited_by_human: bool = False

    method_name: str = ""
    file_path: str = ""
    ai_code: str = ""            # última versión escrita por la IA
    first_ai_code: str = ""      # primera versión (para medir la autocorrección)
    code: str = ""               # versión vigente (puede incluir ediciones de QA)
    ai_notes: str = ""
    components_reused: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    components_new: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    unresolved: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    result: str | None = None    # passed | failed | not_built | None
    result_message: str = ""
    first_result: str | None = None
    attempts: int = 0
    duration_ms: int = 0
    azure_id: int | None = None


class Decision(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    at: datetime = Field(default_factory=utcnow)
    user: str
    action: str
    detail: str = ""


class LogEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="run.id", index=True)
    at: datetime = Field(default_factory=utcnow)
    level: str = "info"
    text: str


class Setting(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
