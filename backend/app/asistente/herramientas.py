"""Catalogo de herramientas de Claude para el asistente (paso 19).

Una herramienta de Claude por cada operacion granular del modelo (paso 12,
`app/modelo/edicion.py`) y del dashboard (paso 16, `app/dashboard/edicion.py`),
mas una de solo lectura (`consultar`, el mismo motor de consultas de
siempre) y una para deshacer (`restaurar_version`). El `input_schema` de
cada herramienta sale de `model_json_schema()` de la clase Pydantic que ya
existe: cero esquemas duplicados. El rol decide el catalogo: el
visualizador solo tiene `consultar`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, get_args

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.almacen.base import AlmacenArchivos
from app.catalogo.tablas import RolUsuario, Usuario, Workspace
from app.consultas import consultar, parsear_consulta
from app.consultas.esquema import ConsultaSemantica, FiltroConsulta
from app.dashboard import edicion as dashboard_edicion
from app.dashboard import operaciones as dashboard_operaciones
from app.modelo import edicion as modelo_edicion
from app.modelo import operaciones as modelo_operaciones
from app.nucleo.errores import ErrorApp

EjecutorHerramienta = Callable[[dict[str, Any]], str]

DESCRIPCIONES_MODELO: dict[str, str] = {
    "renombrar_entidad": "Cambia el nombre (y opcionalmente la descripción) de una entidad del modelo.",
    "asignar_tipo_entidad": "Marca una entidad como 'hechos' (registra transacciones) o 'dimension' (catálogo/maestro).",
    "agregar_sinonimo": "Agrega una palabra alternativa con la que se puede nombrar una entidad.",
    "quitar_sinonimo": "Quita un sinónimo de una entidad.",
    "marcar_clave_primaria": "Cambia qué campo o campos son la clave primaria de una entidad.",
    "renombrar_campo": "Cambia el nombre (y descripción) de un campo.",
    "asignar_tipo_semantico": "Cambia el tipo semántico de un campo (monto, cantidad, categoria, fecha, etc.).",
    "confirmar_campo": "Confirma un campo propuesto por la inferencia automática.",
    "rechazar_campo": "Rechaza un campo propuesto: no entra al modelo efectivo ni al dashboard.",
    "crear_relacion": "Crea una relación entre un campo de una entidad y la clave primaria de otra.",
    "confirmar_relacion": "Confirma una relación propuesta por la inferencia automática.",
    "rechazar_relacion": "Rechaza una relación propuesta.",
    "eliminar_relacion": "Elimina una relación del modelo.",
    "crear_metrica": (
        "Crea una métrica nueva: una agregación simple sobre un campo (suma, conteo, conteo_distinto, promedio, "
        "minimo, maximo), un cociente entre dos métricas de agregación, o una fórmula aritmética (suma, resta, "
        "multiplicación, división) entre métricas existentes y constantes numéricas, anidable."
    ),
    "editar_metrica": "Edita el nombre, la expresión o el formato de una métrica existente.",
    "eliminar_metrica": "Elimina una métrica (falla si otra métrica la usa en un cociente o una fórmula).",
    "confirmar_metrica": "Confirma una métrica propuesta.",
    "rechazar_metrica": "Rechaza una métrica propuesta.",
    "agregar_dimension_tiempo": "Declara un campo de fecha como dimensión de tiempo, con las granularidades permitidas.",
    "quitar_dimension_tiempo": "Quita una dimensión de tiempo.",
    "confirmar_todo": "Confirma en bloque todo lo propuesto con confianza suficiente, en una sección o en todo el modelo.",
}

DESCRIPCIONES_DASHBOARD: dict[str, str] = {
    "editar_titulo": "Cambia el título del dashboard.",
    "crear_filtro": "Crea un filtro (rango de fecha o lista de valores) sobre un campo del modelo.",
    "editar_filtro": "Edita la etiqueta o el tipo de un filtro existente.",
    "eliminar_filtro": "Elimina un filtro del dashboard.",
    "crear_kpi": "Crea un KPI (una cifra grande) mostrando una métrica.",
    "editar_kpi": "Cambia el título de un KPI existente.",
    "eliminar_kpi": "Elimina un KPI.",
    "reordenar_kpis": "Cambia el orden de los KPIs (el primero de la lista es el protagonista) sin recrearlos.",
    "crear_grafico": "Crea un gráfico (línea, barras o torta) de una métrica desglosada por una dimensión.",
    "editar_grafico": "Edita el tipo, la métrica, la dimensión, la granularidad o el título de un gráfico.",
    "eliminar_grafico": "Elimina un gráfico.",
    "crear_pestania": "Crea una pestaña del explorador (una tabla) para una entidad, con sus columnas.",
    "editar_pestania": "Edita las columnas, las métricas o el tamaño de página de una pestaña del explorador.",
    "eliminar_pestania": "Elimina una pestaña del explorador.",
}

DESCRIPCION_CONSULTAR = (
    "Consulta los datos reales del workspace: pedí una o más métricas por su id, opcionalmente desglosadas por "
    "dimensiones (con granularidad si son de fecha) y filtradas. Es la ÚNICA forma de saber un número real: "
    "nunca inventes ni calcules a mano un resultado, siempre usá esta herramienta."
)
DESCRIPCION_RESTAURAR = (
    "Deshacer: vuelve a dejar como versión actual el contenido de una versión vieja del modelo o del dashboard. "
    "No borra el historial, crea una versión nueva con ese contenido."
)

ESQUEMA_RESTAURAR: dict[str, Any] = {
    "type": "object",
    "properties": {
        "artefacto": {"type": "string", "enum": ["modelo", "dashboard"], "description": "Qué restaurar: el modelo semántico o el dashboard."},
        "numero": {"type": "integer", "description": "Número de la versión a la que volver."},
    },
    "required": ["artefacto", "numero"],
}


def _esquema_operacion(clase: type[BaseModel]) -> dict[str, Any]:
    """El input_schema de una operacion: el de la clase Pydantic, sacando el
    campo `operacion` (ya esta en el nombre de la herramienta; pedirselo de
    nuevo a Claude es redundante)."""
    esquema = clase.model_json_schema()
    esquema.get("properties", {}).pop("operacion", None)
    if "required" in esquema:
        esquema["required"] = [campo for campo in esquema["required"] if campo != "operacion"]
    return esquema


def _nombre_operacion(clase: type[BaseModel]) -> str:
    return get_args(clase.model_fields["operacion"].annotation)[0]


def _definiciones_de_operaciones(operacion_union: Any, descripciones: dict[str, str]) -> list[tuple[dict[str, Any], type[BaseModel]]]:
    clases = get_args(get_args(operacion_union)[0])
    salida = []
    for clase in clases:
        nombre = _nombre_operacion(clase)
        salida.append(
            (
                {"name": nombre, "description": descripciones.get(nombre, nombre.replace("_", " ")), "input_schema": _esquema_operacion(clase)},
                clase,
            )
        )
    return salida


_OPERACIONES_MODELO = _definiciones_de_operaciones(modelo_edicion.Operacion, DESCRIPCIONES_MODELO)
_OPERACIONES_DASHBOARD = _definiciones_de_operaciones(dashboard_edicion.Operacion, DESCRIPCIONES_DASHBOARD)
_ESQUEMA_CONSULTAR = ConsultaSemantica.model_json_schema()


@dataclass
class CatalogoHerramientas:
    """`definiciones` va tal cual en el parametro `tools` de Claude;
    `ejecutar` aplica la que haya pedido y devuelve el texto para el
    `tool_result` (o levanta ErrorApp, que el motor traduce a un
    `tool_result` con `is_error`)."""

    definiciones: list[dict[str, Any]]
    _ejecutores: dict[str, EjecutorHerramienta] = field(default_factory=dict)

    def ejecutar(self, nombre: str, entrada: dict[str, Any]) -> str:
        ejecutor = self._ejecutores.get(nombre)
        if ejecutor is None:
            raise ErrorApp("E-ASI-03", f"herramienta desconocida: {nombre!r}")
        return ejecutor(entrada)


def _tool_operacion_modelo(nombre: str, sesion: Session, workspace: Workspace, usuario: Usuario) -> EjecutorHerramienta:
    def ejecutar(entrada: dict[str, Any]) -> str:
        version = modelo_operaciones.aplicar_y_guardar(sesion, workspace, {**entrada, "operacion": nombre}, usuario)
        return f"Listo: {version.resumen} (versión {version.numero} del modelo)."

    return ejecutar


def _tool_operacion_dashboard(nombre: str, sesion: Session, workspace: Workspace, usuario: Usuario) -> EjecutorHerramienta:
    def ejecutar(entrada: dict[str, Any]) -> str:
        version = dashboard_operaciones.aplicar_y_guardar(sesion, workspace, {**entrada, "operacion": nombre}, usuario)
        return f"Listo: {version.resumen} (versión {version.numero} del dashboard)."

    return ejecutar


def _tool_consultar(sesion: Session, workspace: Workspace, almacen: AlmacenArchivos, filtros_base: list[FiltroConsulta]) -> EjecutorHerramienta:
    def ejecutar(entrada: dict[str, Any]) -> str:
        modelo, _ = dashboard_operaciones.modelo_efectivo_actual(sesion, workspace)
        consulta = parsear_consulta(entrada)
        if filtros_base:
            consulta = consulta.model_copy(update={"filtros": [*filtros_base, *consulta.filtros]})
        resultado = consultar(sesion, workspace, almacen, modelo, consulta)
        return json.dumps(resultado.como_dict(), ensure_ascii=False, default=str)

    return ejecutar


def _tool_restaurar(sesion: Session, workspace: Workspace, usuario: Usuario) -> EjecutorHerramienta:
    def ejecutar(entrada: dict[str, Any]) -> str:
        numero = entrada["numero"]
        if entrada["artefacto"] == "modelo":
            version = modelo_operaciones.restaurar(sesion, workspace, numero, usuario)
            return f"Se restauró la versión {numero} del modelo (queda como versión {version.numero} nueva)."
        version = dashboard_operaciones.restaurar(sesion, workspace, numero, usuario)
        return f"Se restauró la versión {numero} del dashboard (queda como versión {version.numero} nueva)."

    return ejecutar


def catalogo_para_rol(
    rol: RolUsuario,
    *,
    sesion: Session,
    workspace: Workspace,
    almacen: AlmacenArchivos,
    usuario: Usuario,
    filtros_base: list[FiltroConsulta] | None = None,
) -> CatalogoHerramientas:
    """El catalogo segun el rol de quien pregunta: el visualizador solo
    puede consultar (respetando `filtros_base`, los filtros activos del
    Tablero); el constructor tiene ademas las operaciones de escritura y
    deshacer."""
    definiciones: list[dict[str, Any]] = [{"name": "consultar", "description": DESCRIPCION_CONSULTAR, "input_schema": _ESQUEMA_CONSULTAR}]
    ejecutores: dict[str, EjecutorHerramienta] = {"consultar": _tool_consultar(sesion, workspace, almacen, filtros_base or [])}

    if rol == RolUsuario.CONSTRUCTOR:
        for definicion, _ in _OPERACIONES_MODELO:
            definiciones.append(definicion)
            ejecutores[definicion["name"]] = _tool_operacion_modelo(definicion["name"], sesion, workspace, usuario)
        for definicion, _ in _OPERACIONES_DASHBOARD:
            definiciones.append(definicion)
            ejecutores[definicion["name"]] = _tool_operacion_dashboard(definicion["name"], sesion, workspace, usuario)
        definiciones.append({"name": "restaurar_version", "description": DESCRIPCION_RESTAURAR, "input_schema": ESQUEMA_RESTAURAR})
        ejecutores["restaurar_version"] = _tool_restaurar(sesion, workspace, usuario)

    return CatalogoHerramientas(definiciones=definiciones, _ejecutores=ejecutores)
