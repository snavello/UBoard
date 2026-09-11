"""Operaciones granulares sobre el SpecDashboard (fase 3, paso 16), mismo
patron que `modelo/edicion.py` (paso 12): el wizard de hoy no las necesita
(el spec sale entero del generador o del JSON de "Avanzado"), pero son la
unica forma de que el chat constructor (paso 20) pueda "agregar un grafico"
sin tocar el JSON a mano.

Cada operacion es un nombre + parametros (Pydantic, `extra="forbid"`), se
aplica sobre una copia del spec y devuelve el spec nuevo; la API valida con
`validar_spec` (compila cada panel, igual que `PUT /dashboard`) y guarda una
version con `operacion` y `resumen` (`dashboard/operaciones.py`).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from app.dashboard.esquema import (
    ExploradorSpec,
    FiltroSpec,
    GraficoSpec,
    KpiSpec,
    OrdenGrafico,
    PestaniaSpec,
    SpecDashboard,
    TipoFiltro,
    TipoGrafico,
)
from app.modelo.esquema import Granularidad, IdCorto, RefCampo
from app.nucleo.errores import ErrorApp


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- General ----------
class EditarTitulo(_Base):
    operacion: Literal["editar_titulo"]
    titulo: str = Field(min_length=1, max_length=120)


# ---------- Filtros ----------
class CrearFiltro(_Base):
    operacion: Literal["crear_filtro"]
    id: IdCorto | None = None
    campo: RefCampo
    tipo: TipoFiltro
    etiqueta: str | None = None


class EditarFiltro(_Base):
    operacion: Literal["editar_filtro"]
    filtro: IdCorto
    etiqueta: str | None = None
    tipo: TipoFiltro | None = None


class EliminarFiltro(_Base):
    operacion: Literal["eliminar_filtro"]
    filtro: IdCorto


# ---------- KPIs ----------
class CrearKpi(_Base):
    operacion: Literal["crear_kpi"]
    id: IdCorto | None = None
    metrica: IdCorto
    titulo: str | None = None


class EditarKpi(_Base):
    operacion: Literal["editar_kpi"]
    kpi: IdCorto
    titulo: str | None = None


class EliminarKpi(_Base):
    operacion: Literal["eliminar_kpi"]
    kpi: IdCorto


class ReordenarKpis(_Base):
    """Cambia cual KPI es el protagonista (el primero) sin recrear nada."""

    operacion: Literal["reordenar_kpis"]
    orden: list[IdCorto] = Field(min_length=1)


# ---------- Graficos ----------
class CrearGrafico(_Base):
    operacion: Literal["crear_grafico"]
    id: IdCorto | None = None
    tipo: TipoGrafico
    metrica: IdCorto
    dimension: RefCampo
    granularidad: Granularidad | None = None
    top: int | None = Field(default=None, ge=1, le=100)
    titulo: str | None = None
    orden: OrdenGrafico | None = None


class EditarGrafico(_Base):
    operacion: Literal["editar_grafico"]
    grafico: IdCorto
    tipo: TipoGrafico | None = None
    metrica: IdCorto | None = None
    dimension: RefCampo | None = None
    granularidad: Granularidad | None = None
    top: int | None = Field(default=None, ge=1, le=100)
    titulo: str | None = None
    orden: OrdenGrafico | None = None


class EliminarGrafico(_Base):
    operacion: Literal["eliminar_grafico"]
    grafico: IdCorto


# ---------- Explorador ----------
class CrearPestania(_Base):
    operacion: Literal["crear_pestania"]
    entidad: IdCorto
    titulo: str | None = None
    columnas: list[str] = Field(min_length=1)
    metricas: list[IdCorto] = Field(default_factory=list)
    tamanio_pagina: int = Field(default=25, ge=5, le=200)


class EditarPestania(_Base):
    operacion: Literal["editar_pestania"]
    entidad: IdCorto
    titulo: str | None = None
    columnas: list[str] | None = None
    metricas: list[IdCorto] | None = None
    tamanio_pagina: int | None = Field(default=None, ge=5, le=200)


class EliminarPestania(_Base):
    operacion: Literal["eliminar_pestania"]
    entidad: IdCorto


Operacion = Annotated[
    Union[
        EditarTitulo,
        CrearFiltro,
        EditarFiltro,
        EliminarFiltro,
        CrearKpi,
        EditarKpi,
        EliminarKpi,
        ReordenarKpis,
        CrearGrafico,
        EditarGrafico,
        EliminarGrafico,
        CrearPestania,
        EditarPestania,
        EliminarPestania,
    ],
    Field(discriminator="operacion"),
]

_adaptador = TypeAdapter(Operacion)

OPERACIONES: tuple[str, ...] = tuple(
    sorted(get_args(clase.model_fields["operacion"].annotation)[0] for clase in get_args(get_args(Operacion)[0]))
)


def parsear_operacion(contenido: Any) -> Operacion:
    """Dict -> operacion tipada. Operacion desconocida o parametros invalidos: E-SPEC-07."""
    try:
        return _adaptador.validate_python(contenido)
    except ValidationError as error:
        errores = [
            {"ubicacion": ".".join(str(parte) for parte in e["loc"]) or "operacion", "mensaje": e["msg"]} for e in error.errors()
        ]
        raise ErrorApp("E-SPEC-07", f"{len(errores)} error(es)", extra={"errores": errores, "operaciones": list(OPERACIONES)}) from None


# ---------- Ayudas ----------
def _filtro(spec: SpecDashboard, filtro_id: str) -> FiltroSpec:
    filtro = spec.filtro(filtro_id)
    if filtro is None:
        raise ErrorApp("E-SPEC-08", f"el filtro '{filtro_id}' no existe")
    return filtro


def _kpi(spec: SpecDashboard, kpi_id: str) -> KpiSpec:
    kpi = next((kpi for kpi in spec.kpis if kpi.id == kpi_id), None)
    if kpi is None:
        raise ErrorApp("E-SPEC-08", f"el KPI '{kpi_id}' no existe")
    return kpi


def _grafico(spec: SpecDashboard, grafico_id: str) -> GraficoSpec:
    grafico = spec.grafico(grafico_id)
    if grafico is None:
        raise ErrorApp("E-SPEC-08", f"el gráfico '{grafico_id}' no existe")
    return grafico


def _pestania(spec: SpecDashboard, entidad_id: str) -> PestaniaSpec:
    pestania = spec.pestania(entidad_id)
    if pestania is None:
        raise ErrorApp("E-SPEC-08", f"la pestaña '{entidad_id}' no existe")
    return pestania


def _id_libre(usados: set[str], base: str) -> str:
    candidato = (base or "x")[:60]
    contador = 2
    while candidato in usados:
        candidato = f"{base[:56]}_{contador}"
        contador += 1
    usados.add(candidato)
    return candidato


# ---------- Aplicar ----------
def aplicar_operacion(spec: SpecDashboard, operacion: Operacion) -> tuple[SpecDashboard, str]:
    """Devuelve (spec nuevo, resumen para la version). No valida el resultado:
    eso lo hace quien guarda (`validar_spec`, las mismas tres capas de siempre)."""
    spec = spec.model_copy(deep=True)
    match operacion:
        case EditarTitulo():
            spec.titulo = operacion.titulo
            return spec, f"Título del dashboard: '{operacion.titulo}'"

        case CrearFiltro():
            ids = {f.id for f in spec.filtros} | {k.id for k in spec.kpis} | {g.id for g in spec.graficos}
            identificador = operacion.id or _id_libre(ids, f"f_{operacion.campo.replace('.', '_')}")
            if any(f.id == identificador for f in spec.filtros):
                raise ErrorApp("E-SPEC-08", f"ya existe un filtro con id '{identificador}'")
            spec.filtros.append(FiltroSpec(id=identificador, campo=operacion.campo, tipo=operacion.tipo, etiqueta=operacion.etiqueta))
            return spec, f"Filtro '{identificador}' sobre '{operacion.campo}'"

        case EditarFiltro():
            filtro = _filtro(spec, operacion.filtro)
            if operacion.etiqueta is not None:
                filtro.etiqueta = operacion.etiqueta
            if operacion.tipo is not None:
                filtro.tipo = operacion.tipo
            return spec, f"Filtro '{operacion.filtro}' editado"

        case EliminarFiltro():
            _filtro(spec, operacion.filtro)
            spec.filtros = [f for f in spec.filtros if f.id != operacion.filtro]
            return spec, f"Filtro '{operacion.filtro}' eliminado"

        case CrearKpi():
            ids = {f.id for f in spec.filtros} | {k.id for k in spec.kpis} | {g.id for g in spec.graficos}
            identificador = operacion.id or _id_libre(ids, f"k_{operacion.metrica}")
            if any(k.id == identificador for k in spec.kpis):
                raise ErrorApp("E-SPEC-08", f"ya existe un KPI con id '{identificador}'")
            spec.kpis.append(KpiSpec(id=identificador, metrica=operacion.metrica, titulo=operacion.titulo))
            return spec, f"KPI '{identificador}' con la métrica '{operacion.metrica}'"

        case EditarKpi():
            kpi = _kpi(spec, operacion.kpi)
            if operacion.titulo is not None:
                kpi.titulo = operacion.titulo
            return spec, f"KPI '{operacion.kpi}' editado"

        case EliminarKpi():
            _kpi(spec, operacion.kpi)
            spec.kpis = [k for k in spec.kpis if k.id != operacion.kpi]
            return spec, f"KPI '{operacion.kpi}' eliminado"

        case ReordenarKpis():
            ids_actuales = {k.id for k in spec.kpis}
            faltantes = ids_actuales - set(operacion.orden)
            desconocidos = set(operacion.orden) - ids_actuales
            if desconocidos:
                raise ErrorApp("E-SPEC-08", f"KPI(s) inexistente(s): {', '.join(sorted(desconocidos))}")
            orden = list(operacion.orden) + sorted(faltantes)
            por_id = {k.id: k for k in spec.kpis}
            spec.kpis = [por_id[identificador] for identificador in orden]
            return spec, f"KPIs reordenados: '{orden[0]}' ahora es el protagonista"

        case CrearGrafico():
            ids = {f.id for f in spec.filtros} | {k.id for k in spec.kpis} | {g.id for g in spec.graficos}
            identificador = operacion.id or _id_libre(ids, f"g_{operacion.dimension.replace('.', '_')}")
            if any(g.id == identificador for g in spec.graficos):
                raise ErrorApp("E-SPEC-08", f"ya existe un gráfico con id '{identificador}'")
            spec.graficos.append(
                GraficoSpec(
                    id=identificador,
                    tipo=operacion.tipo,
                    metrica=operacion.metrica,
                    dimension=operacion.dimension,
                    granularidad=operacion.granularidad,
                    top=operacion.top,
                    titulo=operacion.titulo,
                    orden=operacion.orden,
                )
            )
            return spec, f"Gráfico '{identificador}': {operacion.tipo} de '{operacion.metrica}' por '{operacion.dimension}'"

        case EditarGrafico():
            grafico = _grafico(spec, operacion.grafico)
            for campo in ("tipo", "metrica", "dimension", "granularidad", "top", "titulo", "orden"):
                valor = getattr(operacion, campo)
                if valor is not None:
                    setattr(grafico, campo, valor)
            return spec, f"Gráfico '{operacion.grafico}' editado"

        case EliminarGrafico():
            _grafico(spec, operacion.grafico)
            spec.graficos = [g for g in spec.graficos if g.id != operacion.grafico]
            return spec, f"Gráfico '{operacion.grafico}' eliminado"

        case CrearPestania():
            if spec.pestania(operacion.entidad) is not None:
                raise ErrorApp("E-SPEC-08", f"ya existe una pestaña para '{operacion.entidad}'")
            spec.explorador.pestanias.append(
                PestaniaSpec(
                    entidad=operacion.entidad,
                    titulo=operacion.titulo,
                    columnas=operacion.columnas,
                    metricas=operacion.metricas,
                    tamanio_pagina=operacion.tamanio_pagina,
                )
            )
            return spec, f"Pestaña '{operacion.entidad}' creada"

        case EditarPestania():
            pestania = _pestania(spec, operacion.entidad)
            if operacion.titulo is not None:
                pestania.titulo = operacion.titulo
            if operacion.columnas is not None:
                pestania.columnas = operacion.columnas
            if operacion.metricas is not None:
                pestania.metricas = operacion.metricas
            if operacion.tamanio_pagina is not None:
                pestania.tamanio_pagina = operacion.tamanio_pagina
            return spec, f"Pestaña '{operacion.entidad}' editada"

        case EliminarPestania():
            _pestania(spec, operacion.entidad)
            spec.explorador.pestanias = [p for p in spec.explorador.pestanias if p.entidad != operacion.entidad]
            return spec, f"Pestaña '{operacion.entidad}' eliminada"

    raise ErrorApp("E-SPEC-07", f"operacion: {type(operacion).__name__}")  # pragma: no cover
