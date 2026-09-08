"""Validacion del SpecDashboard contra el modelo semantico efectivo.

Ademas de las referencias, cada panel se COMPILA (sin ejecutar) con el
compilador real: si un grafico pide una combinacion que multiplica filas o un
filtro apunta a una entidad sin relacion, falla al cargar el spec, no al
abrir el dashboard.
"""
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from app.consultas.compilador import Compilador
from app.consultas.esquema import FiltroConsulta
from app.dashboard import paneles
from app.dashboard.esquema import SpecDashboard
from app.modelo.esquema import TIPOS_TEMPORALES, ModeloSemantico
from app.nucleo.errores import ErrorApp

JSON_INVALIDO = "SPEC-JSON"
ID_DUPLICADO = "SPEC-ID-DUPLICADO"
FILTRO_CAMPO = "SPEC-FILTRO-CAMPO"
FILTRO_TIPO = "SPEC-FILTRO-TIPO"
KPI_METRICA = "SPEC-KPI-METRICA"
GRAFICO_METRICA = "SPEC-GRAFICO-METRICA"
GRAFICO_DIMENSION = "SPEC-GRAFICO-DIMENSION"
GRAFICO_GRANULARIDAD = "SPEC-GRAFICO-GRANULARIDAD"
PESTANIA_ENTIDAD = "SPEC-PESTANIA-ENTIDAD"
PESTANIA_COLUMNA = "SPEC-PESTANIA-COLUMNA"
PESTANIA_METRICA = "SPEC-PESTANIA-METRICA"
CONSULTA = "SPEC-CONSULTA"


@dataclass
class ErrorValidacion:
    codigo: str
    ubicacion: str
    mensaje: str

    def como_dict(self) -> dict[str, str]:
        return asdict(self)


def parsear_spec(contenido: Any) -> SpecDashboard:
    try:
        return SpecDashboard.model_validate(contenido)
    except ValidationError as error:
        errores = [
            ErrorValidacion(JSON_INVALIDO, ".".join(str(parte) for parte in detalle["loc"]), detalle["msg"])
            for detalle in error.errors()
        ]
        raise error_de_validacion(errores) from None


def error_de_validacion(errores: list[ErrorValidacion]) -> ErrorApp:
    return ErrorApp("E-SPEC-01", f"{len(errores)} error(es)", extra={"errores": [error.como_dict() for error in errores]})


def exigir_valido(errores: list[ErrorValidacion]) -> None:
    if errores:
        raise error_de_validacion(errores)


def _duplicados(ids: list[str]) -> list[str]:
    vistos: set[str] = set()
    return [identificador for identificador in ids if identificador in vistos or vistos.add(identificador)]  # type: ignore[func-returns-value]


def validar_spec(spec: SpecDashboard, modelo: ModeloSemantico) -> list[ErrorValidacion]:
    """`modelo` es el modelo EFECTIVO: lo que no entra al dashboard no puede
    aparecer en el spec."""
    errores: list[ErrorValidacion] = []
    compilador = Compilador(modelo)

    for repetido in _duplicados([f.id for f in spec.filtros] + [k.id for k in spec.kpis] + [g.id for g in spec.graficos]):
        errores.append(ErrorValidacion(ID_DUPLICADO, repetido, f"El id '{repetido}' está repetido en el spec."))
    for repetido in _duplicados([pestania.entidad for pestania in spec.explorador.pestanias]):
        errores.append(ErrorValidacion(ID_DUPLICADO, f"explorador.{repetido}", f"Hay dos pestañas para la entidad '{repetido}'."))

    # Filtros: el conjunto de filtros del spec se prueba sobre cada panel con
    # un valor ficticio, para saber que TODOS los paneles los aceptan.
    filtros_prueba: list[FiltroConsulta] = []
    for filtro in spec.filtros:
        ubicacion = f"filtros.{filtro.id}"
        resuelto = modelo.resolver_campo(filtro.campo)
        if resuelto is None:
            errores.append(ErrorValidacion(FILTRO_CAMPO, ubicacion, f"El filtro '{filtro.id}' usa '{filtro.campo}', que no está en el modelo efectivo."))
            continue
        campo = resuelto[1]
        if filtro.tipo == "rango_fecha" and campo.tipo_dato not in TIPOS_TEMPORALES:
            errores.append(ErrorValidacion(FILTRO_TIPO, ubicacion, f"'{filtro.campo}' es {campo.tipo_dato}; un rango de fecha necesita fecha o fecha_hora."))
            continue
        if filtro.tipo == "lista" and campo.tipo_dato in TIPOS_TEMPORALES:
            errores.append(ErrorValidacion(FILTRO_TIPO, ubicacion, f"'{filtro.campo}' es de fecha; usá un filtro rango_fecha."))
            continue
        if filtro.tipo == "rango_fecha":
            filtros_prueba.append(FiltroConsulta(campo=filtro.campo, operador="entre", valor=["2000-01-01", "2000-12-31"]))
        else:
            filtros_prueba.append(FiltroConsulta(campo=filtro.campo, operador="en", valor=["x"]))

    def compilar(ubicacion: str, armar) -> None:
        try:
            compilador.compilar(armar())
        except ErrorApp as error:
            errores.append(ErrorValidacion(CONSULTA, ubicacion, f"{error.mensaje} ({error.detalle})" if error.detalle else error.mensaje))

    kpis_validos = []
    for kpi in spec.kpis:
        if modelo.metrica(kpi.metrica) is None:
            errores.append(ErrorValidacion(KPI_METRICA, f"kpis.{kpi.id}", f"El KPI '{kpi.id}' usa la métrica '{kpi.metrica}', que no está en el modelo efectivo."))
        else:
            kpis_validos.append(kpi)
    if kpis_validos:
        compilar("kpis", lambda: paneles.consulta_kpis(kpis_validos, filtros_prueba))

    for grafico in spec.graficos:
        ubicacion = f"graficos.{grafico.id}"
        valido = True
        if modelo.metrica(grafico.metrica) is None:
            errores.append(ErrorValidacion(GRAFICO_METRICA, ubicacion, f"El gráfico '{grafico.id}' usa la métrica '{grafico.metrica}', que no está en el modelo efectivo."))
            valido = False
        resuelto = modelo.resolver_campo(grafico.dimension)
        if resuelto is None:
            errores.append(ErrorValidacion(GRAFICO_DIMENSION, ubicacion, f"El gráfico '{grafico.id}' usa la dimensión '{grafico.dimension}', que no está en el modelo efectivo."))
            valido = False
        elif resuelto[1].tipo_dato in TIPOS_TEMPORALES and grafico.granularidad is None:
            errores.append(ErrorValidacion(GRAFICO_GRANULARIDAD, ubicacion, f"El gráfico '{grafico.id}' agrupa por la fecha '{grafico.dimension}': indicá la granularidad (dia, semana, mes, trimestre o anio)."))
            valido = False
        elif resuelto[1].tipo_dato not in TIPOS_TEMPORALES and grafico.granularidad is not None:
            errores.append(ErrorValidacion(GRAFICO_GRANULARIDAD, ubicacion, f"'{grafico.dimension}' no es una fecha: sacá la granularidad."))
            valido = False
        if valido:
            compilar(ubicacion, lambda grafico=grafico: paneles.consulta_grafico(grafico, filtros_prueba))

    for pestania in spec.explorador.pestanias:
        ubicacion = f"explorador.{pestania.entidad}"
        entidad = modelo.entidad(pestania.entidad)
        if entidad is None:
            errores.append(ErrorValidacion(PESTANIA_ENTIDAD, ubicacion, f"La pestaña usa la entidad '{pestania.entidad}', que no existe."))
            continue
        valida = True
        for columna in pestania.columnas:
            referencia = columna if "." in columna else f"{entidad.id}.{columna}"
            if modelo.resolver_campo(referencia) is None:
                errores.append(ErrorValidacion(PESTANIA_COLUMNA, ubicacion, f"La columna '{columna}' de la pestaña '{pestania.entidad}' no está en el modelo efectivo."))
                valida = False
        for metrica_id in pestania.metricas:
            if modelo.metrica(metrica_id) is None:
                errores.append(ErrorValidacion(PESTANIA_METRICA, ubicacion, f"La pestaña '{pestania.entidad}' usa la métrica '{metrica_id}', que no está en el modelo efectivo."))
                valida = False
        if valida:
            compilar(ubicacion, lambda pestania=pestania: paneles.consulta_explorador(modelo, pestania, filtros_prueba)[0])

    return errores
