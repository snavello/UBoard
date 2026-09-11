"""Validacion del modelo semantico, en dos capas:

1. `parsear_modelo`: el JSON respeta el esquema (Pydantic).
2. `validar_estructura`: referencias existentes, claves consistentes, tipos
   compatibles en relaciones y metricas, sin ciclos entre entidades, y lo
   confirmado no depende de lo rechazado.
3. `validar_contra_fuentes`: cada entidad apunta a una fuente ingestada del
   workspace, cada campo a una columna existente y del mismo tipo.

Todas devuelven una lista de ErrorValidacion (vacia = valido); la API las
junta en un E-MOD-01. `modelo_efectivo` es lo que ve el dashboard: solo lo
confirmado o propuesto por encima del umbral.
"""
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from app.modelo.esquema import (
    TIPOS_NUMERICOS,
    TIPOS_TEMPORALES,
    Campo,
    Entidad,
    ExpresionAgregacion,
    ExpresionCociente,
    ExpresionFormula,
    Metrica,
    ModeloSemantico,
    Operando,
    Relacion,
)
from app.nucleo.errores import ErrorApp

# Codigos internos de cada regla (el frontend los muestra junto al mensaje)
JSON_INVALIDO = "MOD-JSON"
ID_DUPLICADO = "MOD-ID-DUPLICADO"
PK_INEXISTENTE = "MOD-PK-INEXISTENTE"
PK_NO_CONFIRMADA = "MOD-PK-NO-CONFIRMADA"
REL_ENTIDAD = "MOD-REL-ENTIDAD"
REL_CAMPO = "MOD-REL-CAMPO"
REL_MISMA_ENTIDAD = "MOD-REL-MISMA-ENTIDAD"
REL_NO_PK = "MOD-REL-NO-PK"
REL_TIPOS = "MOD-REL-TIPOS"
REL_DUPLICADA = "MOD-REL-DUPLICADA"
REL_CICLO = "MOD-REL-CICLO"
REL_CAMPO_NO_EFECTIVO = "MOD-REL-CAMPO-NO-EFECTIVO"
MET_CAMPO = "MOD-MET-CAMPO"
MET_AGREGACION = "MOD-MET-AGREGACION"
MET_COCIENTE = "MOD-MET-COCIENTE"
MET_FORMULA = "MOD-MET-FORMULA"
MET_CAMPO_NO_EFECTIVO = "MOD-MET-CAMPO-NO-EFECTIVO"
TIEMPO_CAMPO = "MOD-TIEMPO-CAMPO"
TIEMPO_TIPO = "MOD-TIEMPO-TIPO"
FUENTE_INEXISTENTE = "MOD-FUENTE-INEXISTENTE"
COLUMNA_INEXISTENTE = "MOD-COLUMNA-INEXISTENTE"
COLUMNA_TIPO = "MOD-COLUMNA-TIPO"

AGREGACIONES_NUMERICAS = frozenset({"suma", "promedio"})
AGREGACIONES_ORDENABLES = frozenset({"minimo", "maximo"})


@dataclass
class ErrorValidacion:
    codigo: str
    ubicacion: str
    mensaje: str

    def como_dict(self) -> dict[str, str]:
        return asdict(self)


def parsear_modelo(contenido: Any) -> ModeloSemantico:
    """JSON -> ModeloSemantico, o E-MOD-01 con los errores de Pydantic."""
    try:
        return ModeloSemantico.model_validate(contenido)
    except ValidationError as error:
        errores = [
            ErrorValidacion(JSON_INVALIDO, ".".join(str(parte) for parte in detalle["loc"]), detalle["msg"])
            for detalle in error.errors()
        ]
        raise error_de_validacion(errores) from None


def error_de_validacion(errores: list[ErrorValidacion]) -> ErrorApp:
    return ErrorApp("E-MOD-01", f"{len(errores)} error(es)", extra={"errores": [error.como_dict() for error in errores]})


def exigir_valido(errores: list[ErrorValidacion]) -> None:
    if errores:
        raise error_de_validacion(errores)


# ---------- Efectividad ----------
def es_efectivo(estado: str, confianza: float, umbral: float) -> bool:
    return estado == "confirmada" or (estado == "propuesta" and confianza >= umbral)


def campo_efectivo(campo: Campo, modelo: ModeloSemantico) -> bool:
    return es_efectivo(campo.estado, campo.confianza, modelo.umbral_confianza)


def relacion_efectiva(relacion: Relacion, modelo: ModeloSemantico) -> bool:
    if not es_efectivo(relacion.estado, relacion.confianza, modelo.umbral_confianza):
        return False
    return all(_campo_referenciado_efectivo(extremo.referencia, modelo) for extremo in (relacion.desde, relacion.hacia))


def _campo_referenciado_efectivo(referencia: str, modelo: ModeloSemantico) -> bool:
    resuelto = modelo.resolver_campo(referencia)
    return resuelto is not None and campo_efectivo(resuelto[1], modelo)


def metrica_efectiva(metrica: Metrica, modelo: ModeloSemantico, vistas: set[str] | None = None) -> bool:
    # Las metricas no tienen confianza: solo cuenta el estado
    if metrica.estado != "confirmada":
        return False
    if isinstance(metrica.expresion, ExpresionAgregacion):
        return _campo_referenciado_efectivo(metrica.expresion.campo, modelo)
    vistas = vistas or set()
    if metrica.id in vistas:
        return False
    if isinstance(metrica.expresion, ExpresionCociente):
        partes = (modelo.metrica(metrica.expresion.numerador), modelo.metrica(metrica.expresion.denominador))
        return all(parte is not None and metrica_efectiva(parte, modelo, vistas | {metrica.id}) for parte in partes)
    return _operando_efectivo(metrica.expresion.izquierda, modelo, vistas | {metrica.id}) and _operando_efectivo(
        metrica.expresion.derecha, modelo, vistas | {metrica.id}
    )


def _operando_efectivo(operando: Operando, modelo: ModeloSemantico, vistas: set[str]) -> bool:
    if isinstance(operando, ExpresionFormula):
        return _operando_efectivo(operando.izquierda, modelo, vistas) and _operando_efectivo(operando.derecha, modelo, vistas)
    if isinstance(operando, (int, float)):
        return True
    otra = modelo.metrica(operando)
    return otra is not None and metrica_efectiva(otra, modelo, vistas)


def modelo_efectivo(modelo: ModeloSemantico) -> ModeloSemantico:
    """Lo que entra al dashboard: campos, relaciones y metricas confirmados o
    propuestos con confianza >= umbral, y solo dimensiones de tiempo sobre
    campos efectivos. Las entidades quedan todas (su clave primaria tiene que
    estar confirmada, ver validar_estructura)."""
    entidades = [
        entidad.model_copy(update={"campos": [campo for campo in entidad.campos if campo_efectivo(campo, modelo)]})
        for entidad in modelo.entidades
    ]
    return modelo.model_copy(
        update={
            "entidades": entidades,
            "relaciones": [relacion for relacion in modelo.relaciones if relacion_efectiva(relacion, modelo)],
            "metricas": [metrica for metrica in modelo.metricas if metrica_efectiva(metrica, modelo)],
            "dimensiones_tiempo": [
                dimension
                for dimension in modelo.dimensiones_tiempo
                if _campo_referenciado_efectivo(dimension.campo, modelo)
            ],
        }
    )


# ---------- Estructura ----------
def validar_estructura(modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores: list[ErrorValidacion] = []
    errores += _validar_ids(modelo)
    errores += _validar_claves_primarias(modelo)
    errores += _validar_relaciones(modelo)
    errores += _validar_metricas(modelo)
    errores += _validar_dimensiones_tiempo(modelo)
    return errores


def _duplicados(ids: list[str]) -> list[str]:
    vistos: set[str] = set()
    repetidos: list[str] = []
    for identificador in ids:
        if identificador in vistos and identificador not in repetidos:
            repetidos.append(identificador)
        vistos.add(identificador)
    return repetidos


def _validar_ids(modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores = []
    for repetido in _duplicados([entidad.id for entidad in modelo.entidades]):
        errores.append(ErrorValidacion(ID_DUPLICADO, f"entidades.{repetido}", f"La entidad '{repetido}' está repetida."))
    for entidad in modelo.entidades:
        for repetido in _duplicados([campo.id for campo in entidad.campos]):
            errores.append(
                ErrorValidacion(ID_DUPLICADO, f"entidades.{entidad.id}.campos.{repetido}", f"El campo '{repetido}' está repetido en '{entidad.id}'.")
            )
    for repetido in _duplicados([relacion.id for relacion in modelo.relaciones]):
        errores.append(ErrorValidacion(ID_DUPLICADO, f"relaciones.{repetido}", f"La relación '{repetido}' está repetida."))
    for repetido in _duplicados([metrica.id for metrica in modelo.metricas]):
        errores.append(ErrorValidacion(ID_DUPLICADO, f"metricas.{repetido}", f"La métrica '{repetido}' está repetida."))
    return errores


def _validar_claves_primarias(modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores = []
    for entidad in modelo.entidades:
        for campo_id in entidad.clave_primaria:
            campo = entidad.campo(campo_id)
            ubicacion = f"entidades.{entidad.id}.clave_primaria"
            if campo is None:
                errores.append(ErrorValidacion(PK_INEXISTENTE, ubicacion, f"La clave primaria de '{entidad.id}' usa el campo '{campo_id}', que no existe."))
            elif campo.estado != "confirmada":
                errores.append(ErrorValidacion(PK_NO_CONFIRMADA, ubicacion, f"El campo '{campo_id}' es clave primaria de '{entidad.id}' y tiene que estar confirmado."))
    return errores


def _validar_relaciones(modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores = []
    pares_vistos: dict[frozenset[str], str] = {}
    grafo: dict[str, list[tuple[str, str]]] = defaultdict(list)  # entidad -> [(vecina, relacion_id)]

    for relacion in modelo.relaciones:
        ubicacion = f"relaciones.{relacion.id}"
        extremos = {}
        for lado, extremo in (("desde", relacion.desde), ("hacia", relacion.hacia)):
            entidad = modelo.entidad(extremo.entidad)
            if entidad is None:
                errores.append(ErrorValidacion(REL_ENTIDAD, ubicacion, f"La relación '{relacion.id}' ({lado}) apunta a la entidad '{extremo.entidad}', que no existe."))
                continue
            campo = entidad.campo(extremo.campo)
            if campo is None:
                errores.append(ErrorValidacion(REL_CAMPO, ubicacion, f"La relación '{relacion.id}' ({lado}) apunta a '{extremo.referencia}', que no existe."))
                continue
            extremos[lado] = (entidad, campo)
        if len(extremos) < 2:
            continue
        (entidad_desde, campo_desde), (entidad_hacia, campo_hacia) = extremos["desde"], extremos["hacia"]

        if entidad_desde.id == entidad_hacia.id:
            errores.append(ErrorValidacion(REL_MISMA_ENTIDAD, ubicacion, f"La relación '{relacion.id}' une '{entidad_desde.id}' consigo misma; en v1 no hay auto-relaciones."))
            continue
        # El lado "1" tiene que ser la clave primaria: si no, el join multiplica filas
        if relacion.cardinalidad in ("n:1", "1:1") and campo_hacia.id not in entidad_hacia.clave_primaria:
            errores.append(ErrorValidacion(REL_NO_PK, ubicacion, f"En '{relacion.id}' ({relacion.cardinalidad}) el destino '{relacion.hacia.referencia}' tiene que ser clave primaria de '{entidad_hacia.id}'."))
        if relacion.cardinalidad in ("1:n", "1:1") and campo_desde.id not in entidad_desde.clave_primaria:
            errores.append(ErrorValidacion(REL_NO_PK, ubicacion, f"En '{relacion.id}' ({relacion.cardinalidad}) el origen '{relacion.desde.referencia}' tiene que ser clave primaria de '{entidad_desde.id}'."))
        if campo_desde.tipo_dato != campo_hacia.tipo_dato:
            errores.append(ErrorValidacion(REL_TIPOS, ubicacion, f"'{relacion.desde.referencia}' es {campo_desde.tipo_dato} y '{relacion.hacia.referencia}' es {campo_hacia.tipo_dato}: no se pueden unir."))
        if relacion.estado == "confirmada" and not (campo_efectivo(campo_desde, modelo) and campo_efectivo(campo_hacia, modelo)):
            errores.append(ErrorValidacion(REL_CAMPO_NO_EFECTIVO, ubicacion, f"La relación '{relacion.id}' está confirmada pero usa un campo rechazado o sin confirmar."))

        if not relacion_efectiva(relacion, modelo):
            continue
        par = frozenset({entidad_desde.id, entidad_hacia.id})
        if par in pares_vistos:
            errores.append(ErrorValidacion(REL_DUPLICADA, ubicacion, f"'{relacion.id}' y '{pares_vistos[par]}' unen las mismas entidades; dejá una sola."))
            continue
        pares_vistos[par] = relacion.id
        grafo[entidad_desde.id].append((entidad_hacia.id, relacion.id))
        grafo[entidad_hacia.id].append((entidad_desde.id, relacion.id))

    errores += _detectar_ciclos(grafo)
    return errores


def _detectar_ciclos(grafo: dict[str, list[tuple[str, str]]]) -> list[ErrorValidacion]:
    """El grafo (no dirigido) de relaciones efectivas tiene que ser un bosque:
    con un ciclo, entre dos entidades hay mas de un camino de joins y el
    compilador no sabe cual elegir. Se reporta un ciclo por componente."""
    errores = []
    visitadas: set[str] = set()
    for inicio in sorted(grafo):
        if inicio in visitadas:
            continue
        # Primero la componente completa (asi no se vuelve a entrar por otra
        # entidad y se reporta el mismo ciclo dos veces), despues el ciclo.
        componente = {inicio}
        pendientes = [inicio]
        while pendientes:
            actual = pendientes.pop()
            for vecina, _ in grafo[actual]:
                if vecina not in componente:
                    componente.add(vecina)
                    pendientes.append(vecina)
        visitadas |= componente

        padre: dict[str, tuple[str | None, str | None]] = {inicio: (None, None)}
        pila = [inicio]
        ciclo_reportado = False
        while pila and not ciclo_reportado:
            actual = pila.pop()
            for vecina, relacion_id in grafo[actual]:
                if relacion_id == padre[actual][1]:
                    continue
                if vecina in padre:
                    camino = _camino(padre, actual, vecina)
                    errores.append(
                        ErrorValidacion(REL_CICLO, "relaciones", f"Hay un ciclo de relaciones entre {', '.join(camino)}: cortá una relación (o marcala como rechazada).")
                    )
                    ciclo_reportado = True
                    break
                padre[vecina] = (actual, relacion_id)
                pila.append(vecina)
    return errores


def _camino(padre: dict[str, tuple[str | None, str | None]], desde: str, hasta: str) -> list[str]:
    ancestros = []
    actual: str | None = desde
    while actual is not None:
        ancestros.append(actual)
        if actual == hasta:
            break
        actual = padre[actual][0]
    return sorted(set(ancestros) | {hasta})


def _validar_metricas(modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores = []
    for metrica in modelo.metricas:
        ubicacion = f"metricas.{metrica.id}"
        expresion = metrica.expresion
        if isinstance(expresion, ExpresionAgregacion):
            resuelto = modelo.resolver_campo(expresion.campo)
            if resuelto is None:
                errores.append(ErrorValidacion(MET_CAMPO, ubicacion, f"La métrica '{metrica.id}' usa '{expresion.campo}', que no existe."))
                continue
            _, campo = resuelto
            if expresion.agregacion in AGREGACIONES_NUMERICAS and campo.tipo_dato not in TIPOS_NUMERICOS:
                errores.append(ErrorValidacion(MET_AGREGACION, ubicacion, f"'{expresion.agregacion}' necesita un campo numérico y '{expresion.campo}' es {campo.tipo_dato}."))
            if expresion.agregacion in AGREGACIONES_ORDENABLES and campo.tipo_dato not in TIPOS_NUMERICOS | TIPOS_TEMPORALES:
                errores.append(ErrorValidacion(MET_AGREGACION, ubicacion, f"'{expresion.agregacion}' necesita un campo numérico o de fecha y '{expresion.campo}' es {campo.tipo_dato}."))
            if metrica.estado == "confirmada" and not campo_efectivo(campo, modelo):
                errores.append(ErrorValidacion(MET_CAMPO_NO_EFECTIVO, ubicacion, f"La métrica '{metrica.id}' está confirmada pero '{expresion.campo}' está rechazado o sin confirmar."))
        elif isinstance(expresion, ExpresionCociente):
            errores += _validar_cociente(metrica, expresion, modelo)
        else:
            errores += _validar_formula(metrica, expresion, modelo)
    return errores


def _validar_cociente(metrica: Metrica, expresion: ExpresionCociente, modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores = []
    ubicacion = f"metricas.{metrica.id}"
    for rol, referencia in (("numerador", expresion.numerador), ("denominador", expresion.denominador)):
        if referencia == metrica.id:
            errores.append(ErrorValidacion(MET_COCIENTE, ubicacion, f"La métrica '{metrica.id}' se usa a sí misma como {rol}."))
            continue
        otra = modelo.metrica(referencia)
        if otra is None:
            errores.append(ErrorValidacion(MET_COCIENTE, ubicacion, f"El {rol} '{referencia}' de '{metrica.id}' no es una métrica del modelo."))
        elif isinstance(otra.expresion, ExpresionCociente):
            errores.append(ErrorValidacion(MET_COCIENTE, ubicacion, f"El {rol} '{referencia}' de '{metrica.id}' es a su vez un cociente; en v1 solo se dividen agregaciones."))
        elif metrica.estado == "confirmada" and not metrica_efectiva(otra, modelo):
            errores.append(ErrorValidacion(MET_CAMPO_NO_EFECTIVO, ubicacion, f"La métrica '{metrica.id}' está confirmada pero su {rol} '{referencia}' no."))
    return errores


def _validar_formula(metrica: Metrica, expresion: ExpresionFormula, modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores: list[ErrorValidacion] = []
    _validar_operando(metrica, expresion.izquierda, modelo, {metrica.id}, errores)
    _validar_operando(metrica, expresion.derecha, modelo, {metrica.id}, errores)
    return errores


def _validar_operando(metrica: Metrica, operando: Operando, modelo: ModeloSemantico, vistos: set[str], errores: list[ErrorValidacion]) -> None:
    """Recorre un operando de formula: un numero no necesita nada, una formula
    embebida se recorre igual, y un id de metrica se valida (existe, no es un
    cociente, esta efectiva si la metrica esta confirmada) y sigue bajando si
    a su vez es otra formula, llevando `vistos` para cortar los ciclos."""
    ubicacion = f"metricas.{metrica.id}"
    if isinstance(operando, ExpresionFormula):
        _validar_operando(metrica, operando.izquierda, modelo, vistos, errores)
        _validar_operando(metrica, operando.derecha, modelo, vistos, errores)
        return
    if isinstance(operando, (int, float)):
        return
    if operando in vistos:
        errores.append(ErrorValidacion(MET_FORMULA, ubicacion, f"La fórmula de '{metrica.id}' tiene un ciclo: '{operando}' se termina referenciando a sí misma."))
        return
    otra = modelo.metrica(operando)
    if otra is None:
        errores.append(ErrorValidacion(MET_FORMULA, ubicacion, f"La fórmula de '{metrica.id}' usa '{operando}', que no es una métrica del modelo."))
        return
    if isinstance(otra.expresion, ExpresionCociente):
        errores.append(ErrorValidacion(MET_FORMULA, ubicacion, f"La fórmula de '{metrica.id}' usa '{operando}', que es un cociente; en v1 las fórmulas no dividen cocientes."))
        return
    if metrica.estado == "confirmada" and not metrica_efectiva(otra, modelo):
        errores.append(ErrorValidacion(MET_CAMPO_NO_EFECTIVO, ubicacion, f"La métrica '{metrica.id}' está confirmada pero '{operando}' no."))
    if isinstance(otra.expresion, ExpresionFormula):
        _validar_operando(metrica, otra.expresion.izquierda, modelo, vistos | {operando}, errores)
        _validar_operando(metrica, otra.expresion.derecha, modelo, vistos | {operando}, errores)


def _validar_dimensiones_tiempo(modelo: ModeloSemantico) -> list[ErrorValidacion]:
    errores = []
    for dimension in modelo.dimensiones_tiempo:
        ubicacion = f"dimensiones_tiempo.{dimension.campo}"
        resuelto = modelo.resolver_campo(dimension.campo)
        if resuelto is None:
            errores.append(ErrorValidacion(TIEMPO_CAMPO, ubicacion, f"La dimensión de tiempo usa '{dimension.campo}', que no existe."))
        elif resuelto[1].tipo_dato not in TIPOS_TEMPORALES:
            errores.append(ErrorValidacion(TIEMPO_TIPO, ubicacion, f"'{dimension.campo}' es {resuelto[1].tipo_dato}; una dimensión de tiempo necesita fecha o fecha_hora."))
    return errores


# ---------- Contra las fuentes ----------
def validar_contra_fuentes(modelo: ModeloSemantico, esquemas: dict[str, list[dict[str, Any]]]) -> list[ErrorValidacion]:
    """`esquemas`: nombre_tabla -> esquema de la fuente (lista de columnas con
    nombre y tipo, como lo guarda la ingesta)."""
    errores = []
    for entidad in modelo.entidades:
        columnas = esquemas.get(entidad.fuente)
        if columnas is None:
            errores.append(
                ErrorValidacion(FUENTE_INEXISTENTE, f"entidades.{entidad.id}.fuente", f"La entidad '{entidad.id}' usa la fuente '{entidad.fuente}', que no está cargada en este workspace.")
            )
            continue
        tipos = {columna["nombre"]: columna["tipo"] for columna in columnas}
        for campo in entidad.campos:
            ubicacion = f"entidades.{entidad.id}.campos.{campo.id}"
            if campo.columna_origen not in tipos:
                errores.append(ErrorValidacion(COLUMNA_INEXISTENTE, ubicacion, f"La columna '{campo.columna_origen}' no existe en la fuente '{entidad.fuente}'. Columnas: {', '.join(tipos)}."))
            elif tipos[campo.columna_origen] != campo.tipo_dato:
                errores.append(ErrorValidacion(COLUMNA_TIPO, ubicacion, f"'{entidad.fuente}.{campo.columna_origen}' es {tipos[campo.columna_origen]} en la fuente y el modelo dice {campo.tipo_dato}."))
    return errores
