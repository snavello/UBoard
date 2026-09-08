"""ConsultaSemantica: lo unico que el resto de la app (dashboard, explorador,
preguntas del asistente) le pide al motor. Habla de metricas y campos del
modelo; el compilador la traduce a SQL. Nadie mas escribe SQL."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.modelo.esquema import Granularidad, IdCorto, RefCampo
from app.nucleo.errores import ErrorApp

Operador = Literal[
    "igual",
    "distinto",
    "en",
    "entre",
    "mayor",
    "mayor_igual",
    "menor",
    "menor_igual",
    "contiene",
    "es_nulo",
    "no_es_nulo",
]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FiltroConsulta(_Base):
    campo: RefCampo
    operador: Operador = "igual"
    # escalar para igual/distinto/mayor/...; lista para `en`; [desde, hasta] para
    # `entre` (cualquiera de los dos puede ser null = abierto); nada para es_nulo
    valor: Any = None


class DimensionConsulta(_Base):
    campo: RefCampo
    # Solo para campos fecha/fecha_hora declarados en dimensiones_tiempo
    granularidad: Granularidad | None = None
    # Nombre de la columna en el resultado; por defecto "entidad.campo"
    alias: str | None = Field(default=None, min_length=1, max_length=120)


class OrdenConsulta(_Base):
    # id de metrica, alias de dimension o "entidad.campo"
    por: str = Field(min_length=1)
    direccion: Literal["asc", "desc"] = "asc"


class ConsultaSemantica(_Base):
    # Si se indica, las filas salen de esta entidad (todas, aunque no tengan
    # hechos) y las metricas se le pegan con LEFT JOIN: es el explorador.
    entidad_base: IdCorto | None = None
    metricas: list[IdCorto] = Field(default_factory=list)
    dimensiones: list[DimensionConsulta] = Field(default_factory=list)
    filtros: list[FiltroConsulta] = Field(default_factory=list)
    orden: list[OrdenConsulta] = Field(default_factory=list)
    limite: int | None = Field(default=None, ge=1, le=100_000)
    desplazamiento: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _algo_que_devolver(self) -> "ConsultaSemantica":
        if not self.metricas and not self.dimensiones:
            raise ValueError("la consulta tiene que pedir al menos una métrica o una dimensión")
        return self


def parsear_consulta(contenido: Any) -> ConsultaSemantica:
    try:
        return ConsultaSemantica.model_validate(contenido)
    except ValidationError as error:
        detalle = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors())
        raise ErrorApp("E-CONS-07", detalle) from None
