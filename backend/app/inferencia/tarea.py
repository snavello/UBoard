"""Proponer el modelo como tarea en segundo plano (a pedido, desde el boton
"Proponer modelo" de Fuentes): heuristicas -> Claude (si hay clave) ->
fusion con el modelo actual -> validacion -> version nueva."""
import logging
from typing import Any

import duckdb
from sqlalchemy import select

from app.catalogo.tablas import Fuente, Inferencia, Workspace
from app.consultas.motor import fuentes_listas, obtener_motor
from app.inferencia.fusion import fusionar
from app.inferencia.heuristicas import FuentePerfilada, proponer_modelo
from app.inferencia.llm import ClienteLLM, obtener_cliente_llm
from app.inferencia.semantica import (
    SISTEMA,
    RespuestaSemantica,
    aplicar_semantica,
    armar_pedido,
    consultar_semantica,
    huella_pedido,
    validar_respuesta,
)
from app.ingesta.tipado import columna_sql
from app.modelo import operaciones
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import validar_contra_fuentes, validar_estructura
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp
from app.perfilado import PerfilFuente
from app.tareas import ContextoTarea, registrar_tarea

registro = logging.getLogger("uboard.inferencia")

TIPO_TAREA_PROPONER_MODELO = "inferencia.proponer_modelo"
OPERACION_PROPONER = "proponer_modelo"
TIPO_INFERENCIA_SEMANTICA = "semantica"


def _muestras(conexion: duckdb.DuckDBPyConnection, fuentes: list[Fuente], filas: int) -> dict[str, list[dict[str, Any]]]:
    """Unas filas por tabla, como lista de dicts serializables. Solo si
    ENVIAR_MUESTRA_LLM esta activo."""
    muestras: dict[str, list[dict[str, Any]]] = {}
    for fuente in fuentes:
        resultado = conexion.execute(f"SELECT * FROM {columna_sql(fuente.nombre_tabla)} LIMIT {int(filas)}")
        columnas = [descripcion[0] for descripcion in resultado.description]
        muestras[fuente.nombre_tabla] = [
            {columna: (str(valor) if not isinstance(valor, (int, float, bool, str, type(None))) else valor) for columna, valor in zip(columnas, fila)}
            for fila in resultado.fetchall()
        ]
    return muestras


def enriquecer_con_claude(
    contexto: ContextoTarea,
    workspace: Workspace,
    cliente: ClienteLLM,
    modelo: ModeloSemantico,
    perfiles: dict[str, PerfilFuente],
    muestras: dict[str, list[dict[str, Any]]],
) -> tuple[ModeloSemantico, dict[str, Any]]:
    """Pide la semantica a Claude con cache por huella del pedido en la tabla
    `inferencia`. Devuelve (modelo enriquecido, detalle para el resultado)."""
    modelo_claude = getattr(cliente, "modelo", "?")
    pedido = armar_pedido(modelo, perfiles, muestras)
    huella = huella_pedido(modelo_claude, SISTEMA, pedido)
    guardada = contexto.sesion.scalar(
        select(Inferencia).where(Inferencia.workspace_id == workspace.id, Inferencia.huella == huella)
    )
    if guardada is not None:
        respuesta = RespuestaSemantica.model_validate(guardada.respuesta)
        if not validar_respuesta(modelo, respuesta):
            return aplicar_semantica(modelo, respuesta), {"usado": True, "cache": True, "modelo": guardada.modelo_claude, "tokens_entrada": 0, "tokens_salida": 0}

    respuesta, cruda = consultar_semantica(cliente, modelo, pedido)
    if guardada is None:
        contexto.sesion.add(
            Inferencia(
                workspace_id=workspace.id,
                tipo=TIPO_INFERENCIA_SEMANTICA,
                huella=huella,
                modelo_claude=cruda.modelo,
                respuesta=respuesta.model_dump(mode="json"),
                tokens_entrada=cruda.tokens_entrada,
                tokens_salida=cruda.tokens_salida,
            )
        )
        contexto.sesion.commit()
    return aplicar_semantica(modelo, respuesta), {
        "usado": True,
        "cache": False,
        "modelo": cruda.modelo,
        "tokens_entrada": cruda.tokens_entrada,
        "tokens_salida": cruda.tokens_salida,
    }


@registrar_tarea(TIPO_TAREA_PROPONER_MODELO)
def tarea_proponer_modelo(contexto: ContextoTarea, parametros: dict) -> dict:
    workspace = contexto.sesion.get(Workspace, contexto.workspace_id)
    if workspace is None:
        raise ErrorApp("E-WS-01", f"id: {contexto.workspace_id}")
    fuentes = fuentes_listas(contexto.sesion, workspace)
    if not fuentes:
        raise ErrorApp("E-INF-02", f"workspace: {workspace.id}")
    sin_perfil = [fuente.nombre_tabla for fuente in fuentes if not fuente.perfil]
    if sin_perfil:
        raise ErrorApp("E-INF-03", "fuentes: " + ", ".join(sin_perfil))

    configuracion = obtener_configuracion()
    contexto.informar(10, "Buscando claves y relaciones")
    perfiles = {fuente.nombre_tabla: PerfilFuente.model_validate(fuente.perfil) for fuente in fuentes}
    perfiladas = [FuentePerfilada(fuente.nombre_tabla, fuente.esquema, perfiles[fuente.nombre_tabla]) for fuente in fuentes]
    conexion = obtener_motor().conexion(workspace.id, fuentes, contexto.almacen)
    try:
        propuesta = proponer_modelo(
            conexion,
            perfiladas,
            umbral_inclusion=configuracion.umbral_inclusion_fk,
            umbral_nombre=configuracion.umbral_similitud_nombre,
        )
        muestras = _muestras(conexion, fuentes, configuracion.filas_muestra_llm) if configuracion.enviar_muestra_llm else {}
    finally:
        conexion.close()

    claude: dict[str, Any] = {"usado": False, "cache": False}
    cliente = obtener_cliente_llm()
    if cliente is None:
        claude["advertencia"] = "Sin clave de Anthropic configurada: la propuesta es solo heurística."
    else:
        contexto.informar(40, "Consultando a Claude")
        try:
            propuesta, claude = enriquecer_con_claude(contexto, workspace, cliente, propuesta, perfiles, muestras)
        except ErrorApp as error:
            registro.warning("Claude no aporto semantica: %s", error)
            claude["advertencia"] = f"{error.codigo}: {error.mensaje}"

    contexto.informar(70, "Fusionando con el modelo actual")
    version_anterior = operaciones.version_actual(contexto.sesion, workspace)
    modelo = fusionar(operaciones.modelo_de(version_anterior) if version_anterior else None, propuesta)

    contexto.informar(85, "Validando")
    errores = validar_estructura(modelo)
    if not errores:
        errores = validar_contra_fuentes(modelo, operaciones.esquemas_del_workspace(contexto.sesion, workspace))
    if errores:
        raise ErrorApp("E-INF-04", "; ".join(f"{error.codigo} {error.ubicacion}" for error in errores[:5]))

    version = operaciones.guardar_version(
        contexto.sesion, workspace, modelo, operacion=OPERACION_PROPONER, autor_id=contexto.tarea.creada_por_id
    )
    contexto.informar(95, "Listo")
    return {
        "version": version.numero,
        "resumen": modelo.resumen(),
        "claude": claude,
        "entidades": [{"id": entidad.id, "nombre": entidad.nombre, "tipo": entidad.tipo, "clave_primaria": entidad.clave_primaria} for entidad in modelo.entidades],
        "relaciones": [
            {"id": relacion.id, "desde": relacion.desde.referencia, "hacia": relacion.hacia.referencia, "confianza": relacion.confianza, "estado": relacion.estado}
            for relacion in modelo.relaciones
        ],
        "metricas": [{"id": metrica.id, "nombre": metrica.nombre, "estado": metrica.estado, "origen": metrica.origen} for metrica in modelo.metricas],
    }
