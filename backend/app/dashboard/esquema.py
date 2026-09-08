"""SpecDashboard (Pydantic v2), segun §5 de la especificacion.

Todo referencia al modelo semantico: metricas por id, campos como
"entidad.campo". Las columnas del explorador aceptan un campo propio de la
entidad ("nombre") o uno relacionado ("vendedores.nombre").
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modelo.esquema import Granularidad, IdCorto, RefCampo

TipoFiltro = Literal["rango_fecha", "lista"]
TipoGrafico = Literal["linea", "barras", "torta"]
OrdenGrafico = Literal["dimension", "metrica"]


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FiltroSpec(_Base):
    id: IdCorto
    campo: RefCampo
    tipo: TipoFiltro
    etiqueta: str | None = None


class KpiSpec(_Base):
    id: IdCorto
    metrica: IdCorto
    titulo: str | None = None


class GraficoSpec(_Base):
    id: IdCorto
    tipo: TipoGrafico
    metrica: IdCorto
    dimension: RefCampo
    # Obligatoria si la dimension es de fecha
    granularidad: Granularidad | None = None
    top: int | None = Field(default=None, ge=1, le=100)
    titulo: str | None = None
    # Por defecto: linea por dimension ascendente; barras y torta por metrica descendente
    orden: OrdenGrafico | None = None

    @property
    def orden_efectivo(self) -> OrdenGrafico:
        return self.orden or ("dimension" if self.tipo == "linea" else "metrica")


class PestaniaSpec(_Base):
    entidad: IdCorto
    titulo: str | None = None
    # ids de campos propios o "entidad.campo" relacionados
    columnas: list[str] = Field(min_length=1)
    metricas: list[IdCorto] = Field(default_factory=list)
    tamanio_pagina: int = Field(default=25, ge=5, le=200)


class ExploradorSpec(_Base):
    pestanias: list[PestaniaSpec] = Field(default_factory=list)


class SpecDashboard(_Base):
    version: int = Field(default=1, ge=1)
    # Version del modelo contra la que se valido; la fija el servidor al guardar
    modelo_version: int | None = None
    titulo: str | None = None
    filtros: list[FiltroSpec] = Field(default_factory=list)
    kpis: list[KpiSpec] = Field(default_factory=list)
    graficos: list[GraficoSpec] = Field(default_factory=list)
    explorador: ExploradorSpec = Field(default_factory=ExploradorSpec)

    def filtro(self, filtro_id: str) -> FiltroSpec | None:
        return next((filtro for filtro in self.filtros if filtro.id == filtro_id), None)

    def grafico(self, grafico_id: str) -> GraficoSpec | None:
        return next((grafico for grafico in self.graficos if grafico.id == grafico_id), None)

    def pestania(self, entidad_id: str) -> PestaniaSpec | None:
        return next((pestania for pestania in self.explorador.pestanias if pestania.entidad == entidad_id), None)

    def resumen(self) -> str:
        return (
            f"{len(self.filtros)} filtros, {len(self.kpis)} KPIs, {len(self.graficos)} gráficos, "
            f"{len(self.explorador.pestanias)} pestañas"
        )
