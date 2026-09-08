"""Cada panel del dashboard como ConsultaSemantica. Aca esta la unica
"logica de negocio" del dashboard: que pide un KPI, un grafico o una pestania
del explorador. Sirve tanto para validar el spec (compilando sin ejecutar)
como para responder la API."""
from dataclasses import dataclass

from app.consultas.esquema import ConsultaSemantica, DimensionConsulta, FiltroConsulta, OrdenConsulta
from app.dashboard.esquema import GraficoSpec, KpiSpec, PestaniaSpec
from app.modelo.esquema import ModeloSemantico
from app.nucleo.errores import ErrorApp

LIMITE_OPCIONES = 500


@dataclass
class ColumnaExplorador:
    alias: str
    campo: str  # "entidad.campo"
    oculta: bool


def consulta_kpis(kpis: list[KpiSpec], filtros: list[FiltroConsulta]) -> ConsultaSemantica:
    metricas = list(dict.fromkeys(kpi.metrica for kpi in kpis))
    return ConsultaSemantica(metricas=metricas, filtros=filtros)


def consulta_grafico(grafico: GraficoSpec, filtros: list[FiltroConsulta]) -> ConsultaSemantica:
    orden = (
        [OrdenConsulta(por="dimension", direccion="asc")]
        if grafico.orden_efectivo == "dimension"
        else [OrdenConsulta(por=grafico.metrica, direccion="desc")]
    )
    return ConsultaSemantica(
        metricas=[grafico.metrica],
        dimensiones=[DimensionConsulta(campo=grafico.dimension, granularidad=grafico.granularidad, alias="dimension")],
        filtros=filtros,
        orden=orden,
        limite=grafico.top,
    )


def columnas_explorador(modelo: ModeloSemantico, pestania: PestaniaSpec) -> list[ColumnaExplorador]:
    """Resuelve las columnas de la pestania y antepone la clave primaria de la
    entidad (oculta si no se pidio) para que dos filas iguales no se fundan al
    agrupar."""
    entidad = modelo.entidad(pestania.entidad)
    if entidad is None:
        raise ErrorApp("E-CONS-01", f"entidad: {pestania.entidad!r}")
    pedidas: list[ColumnaExplorador] = []
    for columna in pestania.columnas:
        referencia = columna if "." in columna else f"{entidad.id}.{columna}"
        if modelo.resolver_campo(referencia) is None:
            raise ErrorApp("E-CONS-01", f"columna: {columna!r} en la pestaña {entidad.id}")
        pedidas.append(ColumnaExplorador(alias=columna, campo=referencia, oculta=False))
    claves = []
    for campo_pk in entidad.clave_primaria:
        referencia = f"{entidad.id}.{campo_pk}"
        if not any(pedida.campo == referencia for pedida in pedidas):
            claves.append(ColumnaExplorador(alias=f"__pk_{campo_pk}", campo=referencia, oculta=True))
    return claves + pedidas


def consulta_explorador(
    modelo: ModeloSemantico,
    pestania: PestaniaSpec,
    filtros: list[FiltroConsulta],
    *,
    pagina: int = 1,
    tamanio: int | None = None,
    orden_por: str | None = None,
    direccion: str = "asc",
) -> tuple[ConsultaSemantica, list[ColumnaExplorador]]:
    columnas = columnas_explorador(modelo, pestania)
    tamanio = tamanio or pestania.tamanio_pagina
    nombres_validos = {columna.alias for columna in columnas} | set(pestania.metricas)
    if orden_por is not None and orden_por not in nombres_validos:
        raise ErrorApp("E-CONS-08", f"orden por {orden_por!r}")
    por = orden_por or columnas[0].alias
    consulta = ConsultaSemantica(
        entidad_base=pestania.entidad,
        metricas=list(pestania.metricas),
        dimensiones=[DimensionConsulta(campo=columna.campo, alias=columna.alias) for columna in columnas],
        filtros=filtros,
        orden=[OrdenConsulta(por=por, direccion=direccion)],
        limite=tamanio,
        desplazamiento=(pagina - 1) * tamanio,
    )
    return consulta, columnas


def consulta_opciones_lista(campo: str) -> ConsultaSemantica:
    return ConsultaSemantica(dimensiones=[DimensionConsulta(campo=campo, alias="valor")], limite=LIMITE_OPCIONES)


def modelo_con_rango(modelo: ModeloSemantico, campo: str) -> tuple[ModeloSemantico, ConsultaSemantica]:
    """Para el rango de un filtro de fecha hacen falta minimo y maximo del
    campo: se agregan dos metricas efimeras al modelo (en memoria, nunca se
    guardan) y se consulta como cualquier KPI. Sin SQL a mano."""
    from app.modelo.esquema import ExpresionAgregacion, Metrica

    minimo = Metrica(id="rango_minimo", nombre="Mínimo", expresion=ExpresionAgregacion(agregacion="minimo", campo=campo))
    maximo = Metrica(id="rango_maximo", nombre="Máximo", expresion=ExpresionAgregacion(agregacion="maximo", campo=campo))
    ampliado = modelo.model_copy(update={"metricas": [*modelo.metricas, minimo, maximo]})
    return ampliado, ConsultaSemantica(metricas=["rango_minimo", "rango_maximo"])
