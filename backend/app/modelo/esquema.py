"""Esquema del ModeloSemantico (Pydantic v2), segun §4 de la especificacion.

Convenciones:
- Los ids (entidades, campos, relaciones, metricas) son identificadores
  cortos en minusculas: `ventas`, `id_vendedor`, `total_ventas`.
- Un campo se referencia desde afuera de su entidad como "entidad.campo".
- `Entidad.fuente` es el `nombre_tabla` de la fuente ingestada (la vista
  DuckDB); `Campo.columna_origen` es el nombre normalizado de la columna en el
  Parquet, y `Campo.tipo_dato` tiene que coincidir con el tipo del esquema de
  la fuente.
- Todo modelo con `extra="forbid"`: un JSON escrito a mano con una clave mal
  escrita falla al cargar, no en silencio.
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

IdCorto = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,59}$")]
RefCampo = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,59}\.[a-z][a-z0-9_]{0,59}$")]

TipoDato = Literal["entero", "decimal", "fecha", "fecha_hora", "booleano", "texto"]
TipoSemantico = Literal[
    "identificador",
    "clave_foranea",
    "fecha",
    "monto",
    "cantidad",
    "porcentaje",
    "categoria",
    "texto_libre",
    "booleano",
    "geo",
]
Origen = Literal["heuristica", "llm", "usuario"]
Estado = Literal["propuesta", "confirmada", "rechazada"]
TipoEntidad = Literal["hechos", "dimension"]
Cardinalidad = Literal["n:1", "1:1", "1:n"]
Agregacion = Literal["suma", "conteo", "conteo_distinto", "promedio", "minimo", "maximo"]
Formato = Literal["moneda", "entero", "decimal", "porcentaje"]
Granularidad = Literal["dia", "semana", "mes", "trimestre", "anio"]

GRANULARIDADES: tuple[Granularidad, ...] = ("dia", "semana", "mes", "trimestre", "anio")
TIPOS_NUMERICOS: frozenset[str] = frozenset({"entero", "decimal"})
TIPOS_TEMPORALES: frozenset[str] = frozenset({"fecha", "fecha_hora"})


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Campo(_Base):
    id: IdCorto
    columna_origen: str = Field(min_length=1)
    nombre: str = Field(min_length=1)
    tipo_dato: TipoDato
    tipo_semantico: TipoSemantico
    confianza: float = Field(default=1.0, ge=0.0, le=1.0)
    origen: Origen = "usuario"
    estado: Estado = "confirmada"
    descripcion: str | None = None
    # Por que la heuristica propuso esto (patron, unicidad, inclusion...): se muestra en el wizard
    evidencia: dict[str, Any] = Field(default_factory=dict)


class Entidad(_Base):
    id: IdCorto
    nombre: str = Field(min_length=1)
    fuente: str = Field(min_length=1, description="nombre_tabla de la fuente ingestada")
    tipo: TipoEntidad
    clave_primaria: list[IdCorto] = Field(min_length=1)
    campos: list[Campo] = Field(min_length=1)
    sinonimos: list[str] = Field(default_factory=list)
    descripcion: str | None = None
    # Quien puso nombre, tipo y sinonimos: la fusion no pisa lo del usuario
    origen: Origen = "usuario"

    def campo(self, campo_id: str) -> Campo | None:
        return next((campo for campo in self.campos if campo.id == campo_id), None)


class ExtremoRelacion(_Base):
    entidad: IdCorto
    campo: IdCorto

    @property
    def referencia(self) -> str:
        return f"{self.entidad}.{self.campo}"


class Relacion(_Base):
    id: IdCorto
    desde: ExtremoRelacion
    hacia: ExtremoRelacion
    cardinalidad: Cardinalidad = "n:1"
    confianza: float = Field(default=1.0, ge=0.0, le=1.0)
    evidencia: dict[str, Any] = Field(default_factory=dict)
    estado: Estado = "confirmada"
    # Para el filtrado asociativo (fase 4): una relacion puede unir sin propagar filtros
    propagar: bool = True


class ExpresionAgregacion(_Base):
    agregacion: Agregacion
    campo: RefCampo


class ExpresionCociente(_Base):
    """numerador / denominador, ambos ids de metricas de agregacion."""

    numerador: IdCorto
    denominador: IdCorto


OperacionFormula = Literal["suma", "resta", "multiplicacion", "division"]


class ExpresionFormula(_Base):
    """Arbol de operaciones aritmeticas entre metricas (de agregacion u otras
    formulas, anidando) y constantes numericas. Cada operando es un id de
    metrica, un numero o, para anidar, otra ExpresionFormula embebida."""

    operacion: OperacionFormula
    izquierda: "Operando"
    derecha: "Operando"


Operando = IdCorto | float | ExpresionFormula
ExpresionFormula.model_rebuild()


class Metrica(_Base):
    id: IdCorto
    nombre: str = Field(min_length=1)
    expresion: ExpresionAgregacion | ExpresionCociente | ExpresionFormula
    formato: Formato = "decimal"
    confianza: float = Field(default=1.0, ge=0.0, le=1.0)
    origen: Origen = "usuario"
    estado: Estado = "confirmada"
    descripcion: str | None = None


class DimensionTiempo(_Base):
    campo: RefCampo
    granularidades: list[Granularidad] = Field(default_factory=lambda: list(GRANULARIDADES), min_length=1)


class ModeloSemantico(_Base):
    version: int = Field(default=1, ge=1)
    entidades: list[Entidad] = Field(min_length=1)
    relaciones: list[Relacion] = Field(default_factory=list)
    metricas: list[Metrica] = Field(default_factory=list)
    dimensiones_tiempo: list[DimensionTiempo] = Field(default_factory=list)
    # Lo propuesto con confianza >= umbral entra al dashboard aunque nadie lo confirme
    umbral_confianza: float = Field(default=0.9, ge=0.0, le=1.0)

    def entidad(self, entidad_id: str) -> Entidad | None:
        return next((entidad for entidad in self.entidades if entidad.id == entidad_id), None)

    def metrica(self, metrica_id: str) -> Metrica | None:
        return next((metrica for metrica in self.metricas if metrica.id == metrica_id), None)

    def resolver_campo(self, referencia: str) -> tuple[Entidad, Campo] | None:
        """'ventas.monto' -> (Entidad ventas, Campo monto), o None."""
        entidad_id, _, campo_id = referencia.partition(".")
        entidad = self.entidad(entidad_id)
        if entidad is None:
            return None
        campo = entidad.campo(campo_id)
        if campo is None:
            return None
        return entidad, campo

    def resumen(self) -> str:
        return (
            f"{len(self.entidades)} entidades, {len(self.relaciones)} relaciones, "
            f"{len(self.metricas)} métricas, {len(self.dimensiones_tiempo)} dimensiones de tiempo"
        )
