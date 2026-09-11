"""Operaciones granulares sobre el modelo semantico (§4 de la especificacion,
mas las que exige el semaforo del wizard). Son las mismas para el wizard
(fase 2) y para el chat (fase 3): cada una es un nombre + parametros
(Pydantic, `extra="forbid"`), se aplica sobre una copia del modelo y devuelve
el modelo nuevo; la API valida las tres capas y guarda una version con
`operacion` y `diff`. Deshacer (fase 3) = volver al contenido de la version
anterior.

Convencion: lo que toca el usuario queda con `origen: usuario`; confirmar o
rechazar cambia `estado` y no el origen (la evidencia sigue siendo de quien
lo propuso).
"""
from __future__ import annotations

from typing import Annotated, Any, Literal, Union, get_args

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from app.modelo.esquema import (
    GRANULARIDADES,
    Cardinalidad,
    Campo,
    DimensionTiempo,
    Entidad,
    ExpresionAgregacion,
    ExpresionCociente,
    ExpresionFormula,
    ExtremoRelacion,
    Formato,
    Granularidad,
    IdCorto,
    Metrica,
    ModeloSemantico,
    Operando,
    RefCampo,
    Relacion,
    TipoEntidad,
    TipoSemantico,
)
from app.nucleo.errores import ErrorApp


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------- Entidades ----------
class RenombrarEntidad(_Base):
    operacion: Literal["renombrar_entidad"]
    entidad: IdCorto
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = None


class AsignarTipoEntidad(_Base):
    operacion: Literal["asignar_tipo_entidad"]
    entidad: IdCorto
    tipo: TipoEntidad


class AgregarSinonimo(_Base):
    operacion: Literal["agregar_sinonimo"]
    entidad: IdCorto
    sinonimo: str = Field(min_length=1, max_length=60)


class QuitarSinonimo(_Base):
    operacion: Literal["quitar_sinonimo"]
    entidad: IdCorto
    sinonimo: str


class MarcarClavePrimaria(_Base):
    operacion: Literal["marcar_clave_primaria"]
    entidad: IdCorto
    campos: list[IdCorto] = Field(min_length=1)


# ---------- Campos ----------
class RenombrarCampo(_Base):
    operacion: Literal["renombrar_campo"]
    entidad: IdCorto
    campo: IdCorto
    nombre: str = Field(min_length=1, max_length=80)
    descripcion: str | None = None


class AsignarTipoSemantico(_Base):
    operacion: Literal["asignar_tipo_semantico"]
    entidad: IdCorto
    campo: IdCorto
    tipo_semantico: TipoSemantico


class ConfirmarCampo(_Base):
    operacion: Literal["confirmar_campo"]
    entidad: IdCorto
    campo: IdCorto


class RechazarCampo(_Base):
    operacion: Literal["rechazar_campo"]
    entidad: IdCorto
    campo: IdCorto


# ---------- Relaciones ----------
class CrearRelacion(_Base):
    operacion: Literal["crear_relacion"]
    id: IdCorto | None = None
    desde: ExtremoRelacion
    hacia: ExtremoRelacion
    cardinalidad: Cardinalidad = "n:1"


class ConfirmarRelacion(_Base):
    operacion: Literal["confirmar_relacion"]
    relacion: IdCorto


class RechazarRelacion(_Base):
    operacion: Literal["rechazar_relacion"]
    relacion: IdCorto


class EliminarRelacion(_Base):
    operacion: Literal["eliminar_relacion"]
    relacion: IdCorto


# ---------- Metricas ----------
class CrearMetrica(_Base):
    operacion: Literal["crear_metrica"]
    id: IdCorto
    nombre: str = Field(min_length=1, max_length=80)
    expresion: ExpresionAgregacion | ExpresionCociente | ExpresionFormula
    formato: Formato = "decimal"
    descripcion: str | None = None


class EditarMetrica(_Base):
    operacion: Literal["editar_metrica"]
    metrica: IdCorto
    nombre: str | None = Field(default=None, min_length=1, max_length=80)
    expresion: ExpresionAgregacion | ExpresionCociente | ExpresionFormula | None = None
    formato: Formato | None = None
    descripcion: str | None = None


class EliminarMetrica(_Base):
    operacion: Literal["eliminar_metrica"]
    metrica: IdCorto


class ConfirmarMetrica(_Base):
    operacion: Literal["confirmar_metrica"]
    metrica: IdCorto


class RechazarMetrica(_Base):
    operacion: Literal["rechazar_metrica"]
    metrica: IdCorto


# ---------- Dimensiones de tiempo ----------
class AgregarDimensionTiempo(_Base):
    operacion: Literal["agregar_dimension_tiempo"]
    campo: RefCampo
    granularidades: list[Granularidad] = Field(default_factory=lambda: list(GRANULARIDADES), min_length=1)


class QuitarDimensionTiempo(_Base):
    operacion: Literal["quitar_dimension_tiempo"]
    campo: RefCampo


# ---------- En bloque ----------
class ConfirmarTodo(_Base):
    """'Confirmar todo lo verde': lo propuesto con confianza >= minimo en una
    seccion (o en todas), opcionalmente de una sola entidad."""

    operacion: Literal["confirmar_todo"]
    seccion: Literal["campos", "relaciones", "metricas", "todo"] = "todo"
    minimo_confianza: float = Field(default=0.9, ge=0.0, le=1.0)
    entidad: IdCorto | None = None


Operacion = Annotated[
    Union[
        RenombrarEntidad,
        AsignarTipoEntidad,
        AgregarSinonimo,
        QuitarSinonimo,
        MarcarClavePrimaria,
        RenombrarCampo,
        AsignarTipoSemantico,
        ConfirmarCampo,
        RechazarCampo,
        CrearRelacion,
        ConfirmarRelacion,
        RechazarRelacion,
        EliminarRelacion,
        CrearMetrica,
        EditarMetrica,
        EliminarMetrica,
        ConfirmarMetrica,
        RechazarMetrica,
        AgregarDimensionTiempo,
        QuitarDimensionTiempo,
        ConfirmarTodo,
    ],
    Field(discriminator="operacion"),
]

_adaptador = TypeAdapter(Operacion)

OPERACIONES: tuple[str, ...] = tuple(
    sorted(get_args(clase.model_fields["operacion"].annotation)[0] for clase in get_args(get_args(Operacion)[0]))
)


def parsear_operacion(contenido: Any) -> Operacion:
    """Dict -> operacion tipada. Operacion desconocida o parametros invalidos: E-MOD-04."""
    from pydantic import ValidationError

    try:
        return _adaptador.validate_python(contenido)
    except ValidationError as error:
        errores = [
            {"ubicacion": ".".join(str(parte) for parte in e["loc"]) or "operacion", "mensaje": e["msg"]} for e in error.errors()
        ]
        raise ErrorApp("E-MOD-04", f"{len(errores)} error(es)", extra={"errores": errores, "operaciones": list(OPERACIONES)}) from None


# ---------- Ayudas ----------
def _entidad(modelo: ModeloSemantico, entidad_id: str) -> Entidad:
    entidad = modelo.entidad(entidad_id)
    if entidad is None:
        raise ErrorApp("E-MOD-05", f"la entidad '{entidad_id}' no existe")
    return entidad


def _campo(modelo: ModeloSemantico, entidad_id: str, campo_id: str) -> tuple[Entidad, Campo]:
    entidad = _entidad(modelo, entidad_id)
    campo = entidad.campo(campo_id)
    if campo is None:
        raise ErrorApp("E-MOD-05", f"el campo '{entidad_id}.{campo_id}' no existe")
    return entidad, campo


def _relacion(modelo: ModeloSemantico, relacion_id: str) -> Relacion:
    relacion = next((relacion for relacion in modelo.relaciones if relacion.id == relacion_id), None)
    if relacion is None:
        raise ErrorApp("E-MOD-05", f"la relación '{relacion_id}' no existe")
    return relacion


def _metrica(modelo: ModeloSemantico, metrica_id: str) -> Metrica:
    metrica = modelo.metrica(metrica_id)
    if metrica is None:
        raise ErrorApp("E-MOD-05", f"la métrica '{metrica_id}' no existe")
    return metrica


def _id_relacion_libre(modelo: ModeloSemantico, base: str) -> str:
    usados = {relacion.id for relacion in modelo.relaciones}
    candidato = base[:60]
    contador = 2
    while candidato in usados:
        candidato = f"{base[:56]}_{contador}"
        contador += 1
    return candidato


# ---------- Aplicar ----------
def aplicar_operacion(modelo: ModeloSemantico, operacion: Operacion) -> tuple[ModeloSemantico, str]:
    """Devuelve (modelo nuevo, resumen para la version). No valida el modelo
    resultante: eso lo hace quien guarda (las tres capas de siempre)."""
    modelo = modelo.model_copy(deep=True)
    match operacion:
        case RenombrarEntidad():
            entidad = _entidad(modelo, operacion.entidad)
            entidad.nombre = operacion.nombre
            if operacion.descripcion is not None:
                entidad.descripcion = operacion.descripcion
            entidad.origen = "usuario"
            return modelo, f"Entidad '{operacion.entidad}' renombrada a '{operacion.nombre}'"

        case AsignarTipoEntidad():
            entidad = _entidad(modelo, operacion.entidad)
            entidad.tipo = operacion.tipo
            entidad.origen = "usuario"
            return modelo, f"'{operacion.entidad}' marcada como {operacion.tipo}"

        case AgregarSinonimo():
            entidad = _entidad(modelo, operacion.entidad)
            if operacion.sinonimo not in entidad.sinonimos:
                entidad.sinonimos.append(operacion.sinonimo)
            return modelo, f"Sinónimo '{operacion.sinonimo}' en '{operacion.entidad}'"

        case QuitarSinonimo():
            entidad = _entidad(modelo, operacion.entidad)
            entidad.sinonimos = [sinonimo for sinonimo in entidad.sinonimos if sinonimo != operacion.sinonimo]
            return modelo, f"Sinónimo '{operacion.sinonimo}' quitado de '{operacion.entidad}'"

        case MarcarClavePrimaria():
            entidad = _entidad(modelo, operacion.entidad)
            for campo_id in operacion.campos:
                _, campo = _campo(modelo, operacion.entidad, campo_id)
                campo.estado = "confirmada"
                campo.tipo_semantico = "identificador"
                campo.origen = "usuario"
            entidad.clave_primaria = list(operacion.campos)
            return modelo, f"Clave primaria de '{operacion.entidad}': {', '.join(operacion.campos)}"

        case RenombrarCampo():
            _, campo = _campo(modelo, operacion.entidad, operacion.campo)
            campo.nombre = operacion.nombre
            if operacion.descripcion is not None:
                campo.descripcion = operacion.descripcion
            campo.origen = "usuario"
            return modelo, f"Campo '{operacion.entidad}.{operacion.campo}' renombrado a '{operacion.nombre}'"

        case AsignarTipoSemantico():
            entidad, campo = _campo(modelo, operacion.entidad, operacion.campo)
            if campo.id in entidad.clave_primaria and operacion.tipo_semantico != "identificador":
                raise ErrorApp("E-MOD-05", f"'{operacion.entidad}.{operacion.campo}' es clave primaria: su tipo es identificador")
            campo.tipo_semantico = operacion.tipo_semantico
            campo.origen = "usuario"
            campo.confianza = 1.0
            return modelo, f"'{operacion.entidad}.{operacion.campo}' es {operacion.tipo_semantico}"

        case ConfirmarCampo():
            _, campo = _campo(modelo, operacion.entidad, operacion.campo)
            campo.estado = "confirmada"
            return modelo, f"Campo '{operacion.entidad}.{operacion.campo}' confirmado"

        case RechazarCampo():
            entidad, campo = _campo(modelo, operacion.entidad, operacion.campo)
            if campo.id in entidad.clave_primaria:
                raise ErrorApp("E-MOD-05", f"'{operacion.entidad}.{operacion.campo}' es clave primaria: marcá otra clave antes de rechazarlo")
            campo.estado = "rechazada"
            return modelo, f"Campo '{operacion.entidad}.{operacion.campo}' rechazado"

        case CrearRelacion():
            _campo(modelo, operacion.desde.entidad, operacion.desde.campo)
            _campo(modelo, operacion.hacia.entidad, operacion.hacia.campo)
            for existente in modelo.relaciones:
                if existente.desde == operacion.desde and existente.hacia == operacion.hacia:
                    raise ErrorApp("E-MOD-05", f"ya existe la relación '{existente.id}' entre esos campos")
            identificador = operacion.id or _id_relacion_libre(modelo, f"{operacion.desde.entidad}_{operacion.desde.campo}")
            if any(relacion.id == identificador for relacion in modelo.relaciones):
                raise ErrorApp("E-MOD-05", f"ya hay una relación con id '{identificador}'")
            modelo.relaciones.append(
                Relacion(
                    id=identificador,
                    desde=operacion.desde,
                    hacia=operacion.hacia,
                    cardinalidad=operacion.cardinalidad,
                    confianza=1.0,
                    evidencia={"origen": "usuario"},
                    estado="confirmada",
                )
            )
            _, campo_desde = _campo(modelo, operacion.desde.entidad, operacion.desde.campo)
            if operacion.cardinalidad == "n:1":
                campo_desde.tipo_semantico = "clave_foranea"
                campo_desde.estado = "confirmada"
            return modelo, f"Relación '{identificador}': {operacion.desde.referencia} → {operacion.hacia.referencia}"

        case ConfirmarRelacion():
            relacion = _relacion(modelo, operacion.relacion)
            relacion.estado = "confirmada"
            for extremo in (relacion.desde, relacion.hacia):
                _, campo = _campo(modelo, extremo.entidad, extremo.campo)
                if campo.estado != "confirmada":
                    campo.estado = "confirmada"
            return modelo, f"Relación '{operacion.relacion}' confirmada"

        case RechazarRelacion():
            relacion = _relacion(modelo, operacion.relacion)
            relacion.estado = "rechazada"
            return modelo, f"Relación '{operacion.relacion}' rechazada"

        case EliminarRelacion():
            _relacion(modelo, operacion.relacion)
            modelo.relaciones = [relacion for relacion in modelo.relaciones if relacion.id != operacion.relacion]
            return modelo, f"Relación '{operacion.relacion}' eliminada"

        case CrearMetrica():
            if modelo.metrica(operacion.id) is not None:
                raise ErrorApp("E-MOD-05", f"ya existe la métrica '{operacion.id}'")
            modelo.metricas.append(
                Metrica(
                    id=operacion.id,
                    nombre=operacion.nombre,
                    expresion=operacion.expresion,
                    formato=operacion.formato,
                    confianza=1.0,
                    origen="usuario",
                    estado="confirmada",
                    descripcion=operacion.descripcion,
                )
            )
            return modelo, f"Métrica '{operacion.id}' creada"

        case EditarMetrica():
            metrica = _metrica(modelo, operacion.metrica)
            if operacion.nombre is not None:
                metrica.nombre = operacion.nombre
            if operacion.expresion is not None:
                metrica.expresion = operacion.expresion
            if operacion.formato is not None:
                metrica.formato = operacion.formato
            if operacion.descripcion is not None:
                metrica.descripcion = operacion.descripcion
            metrica.origen = "usuario"
            metrica.confianza = 1.0
            return modelo, f"Métrica '{operacion.metrica}' editada"

        case EliminarMetrica():
            _metrica(modelo, operacion.metrica)
            usada_por = [metrica.id for metrica in modelo.metricas if _referencia_metrica(metrica.expresion, operacion.metrica)]
            if usada_por:
                raise ErrorApp("E-MOD-05", f"la métrica '{operacion.metrica}' la usan: {', '.join(usada_por)}")
            modelo.metricas = [metrica for metrica in modelo.metricas if metrica.id != operacion.metrica]
            return modelo, f"Métrica '{operacion.metrica}' eliminada"

        case ConfirmarMetrica():
            metrica = _metrica(modelo, operacion.metrica)
            metrica.estado = "confirmada"
            return modelo, f"Métrica '{operacion.metrica}' confirmada"

        case RechazarMetrica():
            metrica = _metrica(modelo, operacion.metrica)
            metrica.estado = "rechazada"
            return modelo, f"Métrica '{operacion.metrica}' rechazada"

        case AgregarDimensionTiempo():
            if modelo.resolver_campo(operacion.campo) is None:
                raise ErrorApp("E-MOD-05", f"el campo '{operacion.campo}' no existe")
            modelo.dimensiones_tiempo = [dimension for dimension in modelo.dimensiones_tiempo if dimension.campo != operacion.campo]
            modelo.dimensiones_tiempo.append(DimensionTiempo(campo=operacion.campo, granularidades=operacion.granularidades))
            return modelo, f"Dimensión de tiempo '{operacion.campo}'"

        case QuitarDimensionTiempo():
            if not any(dimension.campo == operacion.campo for dimension in modelo.dimensiones_tiempo):
                raise ErrorApp("E-MOD-05", f"'{operacion.campo}' no es una dimensión de tiempo")
            modelo.dimensiones_tiempo = [dimension for dimension in modelo.dimensiones_tiempo if dimension.campo != operacion.campo]
            return modelo, f"Dimensión de tiempo '{operacion.campo}' quitada"

        case ConfirmarTodo():
            confirmados = 0
            minimo = operacion.minimo_confianza
            if operacion.seccion in ("campos", "todo"):
                for entidad in modelo.entidades:
                    if operacion.entidad and entidad.id != operacion.entidad:
                        continue
                    for campo in entidad.campos:
                        if campo.estado == "propuesta" and campo.confianza >= minimo:
                            campo.estado = "confirmada"
                            confirmados += 1
            if operacion.seccion in ("relaciones", "todo"):
                for relacion in modelo.relaciones:
                    if operacion.entidad and operacion.entidad not in (relacion.desde.entidad, relacion.hacia.entidad):
                        continue
                    if relacion.estado == "propuesta" and relacion.confianza >= minimo:
                        relacion.estado = "confirmada"
                        confirmados += 1
                        for extremo in (relacion.desde, relacion.hacia):
                            resuelto = modelo.resolver_campo(extremo.referencia)
                            if resuelto is not None and resuelto[1].estado == "propuesta":
                                resuelto[1].estado = "confirmada"
            if operacion.seccion in ("metricas", "todo"):
                for metrica in modelo.metricas:
                    if operacion.entidad and not _metrica_de_entidad(modelo, metrica, operacion.entidad):
                        continue
                    if metrica.estado == "propuesta" and metrica.confianza >= minimo:
                        metrica.estado = "confirmada"
                        confirmados += 1
            return modelo, f"{confirmados} elemento(s) confirmados en bloque ({operacion.seccion}, confianza ≥ {minimo})"

    raise ErrorApp("E-MOD-04", f"operacion: {type(operacion).__name__}")  # pragma: no cover


def _metrica_de_entidad(modelo: ModeloSemantico, metrica: Metrica, entidad_id: str) -> bool:
    if isinstance(metrica.expresion, ExpresionAgregacion):
        return metrica.expresion.campo.startswith(f"{entidad_id}.")
    if isinstance(metrica.expresion, ExpresionCociente):
        partes = [modelo.metrica(metrica.expresion.numerador), modelo.metrica(metrica.expresion.denominador)]
        return any(parte is not None and _metrica_de_entidad(modelo, parte, entidad_id) for parte in partes)
    return _operando_de_entidad(modelo, metrica.expresion.izquierda, entidad_id) or _operando_de_entidad(modelo, metrica.expresion.derecha, entidad_id)


def _operando_de_entidad(modelo: ModeloSemantico, operando: Operando, entidad_id: str) -> bool:
    if isinstance(operando, ExpresionFormula):
        return _operando_de_entidad(modelo, operando.izquierda, entidad_id) or _operando_de_entidad(modelo, operando.derecha, entidad_id)
    if isinstance(operando, (int, float)):
        return False
    otra = modelo.metrica(operando)
    return otra is not None and _metrica_de_entidad(modelo, otra, entidad_id)


def _referencia_metrica(expresion: ExpresionAgregacion | ExpresionCociente | ExpresionFormula, metrica_id: str) -> bool:
    """Si una metrica usa a otra por su id, en un cociente o en cualquier
    parte de una formula (embebida o por referencia): sirve para saber a
    quien le rompe el modelo eliminar `metrica_id`."""
    if isinstance(expresion, ExpresionCociente):
        return metrica_id in (expresion.numerador, expresion.denominador)
    if isinstance(expresion, ExpresionFormula):
        return _operando_referencia(expresion.izquierda, metrica_id) or _operando_referencia(expresion.derecha, metrica_id)
    return False


def _operando_referencia(operando: Operando, metrica_id: str) -> bool:
    if isinstance(operando, ExpresionFormula):
        return _operando_referencia(operando.izquierda, metrica_id) or _operando_referencia(operando.derecha, metrica_id)
    if isinstance(operando, (int, float)):
        return False
    return operando == metrica_id
