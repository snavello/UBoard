"""Esquema del reporte de calidad de datos (fase 4, "Profundidad")."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


Severidad = Literal["alta", "media", "baja"]


class ProblemaCalidad(_Base):
    # nulos_altos | valores_invalidos | filas_duplicadas | clave_no_unica | huerfanos
    codigo: str
    severidad: Severidad
    # "entidad.campo", el nombre de columna solo, o None si es de toda la fuente
    campo: str | None = None
    mensaje: str
    detalle: dict[str, Any] = Field(default_factory=dict)


class ReporteCalidad(_Base):
    fuente: str
    filas: int
    problemas: list[ProblemaCalidad]
