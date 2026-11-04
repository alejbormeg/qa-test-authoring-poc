"""Contratos de entrada y salida de la IA (también son el esquema de salida estructurada de Claude)."""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


class Paso(BaseModel):
    accion: str = Field(description="Acción del paso, tal como la describe el documento")
    esperado: str = Field(description="Resultado esperado de ese paso; cadena vacía si el documento no lo indica")


class CasoExtraido(BaseModel):
    id: str = Field(description="Identificador del caso en el documento, p. ej. TC-CARRITO-002")
    titulo: str
    precondiciones: str
    pasos: list[Paso]
    datos: str = Field(description="Datos de prueba que menciona el documento para el caso")
    resultado_esperado: str = Field(description="Resultado esperado global, una comprobación por línea")
    avisos: list[str] = Field(description="Problemas que QA debe revisar: ambigüedades, datos que faltan o "
                                          "contradicciones. Lista vacía si el caso está completo")


class Extraccion(BaseModel):
    funcionalidad: str
    feature_ref: str = Field(description="Referencia a la Feature de Azure DevOps si aparece (p. ej. '#103'), o ''")
    version: str = Field(description="Versión del producto si aparece, o ''")
    casos: list[CasoExtraido]
    avisos_generales: list[str]


@dataclass
class CaseInput:
    ext_id: str
    title: str
    preconditions: str
    steps: list[dict[str, str]]
    data: str
    expected: str
    method_name: str


@dataclass
class Generation:
    body: str
    notes: str = ""
    unresolved: list[str] = field(default_factory=list)
    compiled: bool = False


Usage = dict[str, float]
