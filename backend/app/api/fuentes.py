"""Fuentes de un workspace: subir archivos (en segundo plano), listar, ver el
esquema, previsualizar filas y borrar."""
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.almacen import obtener_almacen
from app.almacen.base import AlmacenArchivos
from app.almacen.rutas import ruta_subida_original
from app.api.tareas import TareaSalida, a_tarea_salida
from app.api.workspaces import workspace_del_usuario
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import EstadoFuente, Fuente, RolUsuario, Usuario, Workspace
from app.consultas.motor import fuentes_listas, obtener_motor
from app.ingesta.procesador import eliminar_fuente, validar_extension
from app.ingesta.tarea import TIPO_TAREA_INGESTA
from app.nucleo.auth import exigir_rol
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp
from app.tareas import ColaTareas, encolar_tarea, obtener_cola

router = APIRouter(prefix="/workspaces/{workspace_id}/fuentes", tags=["fuentes"])
solo_constructor = Depends(exigir_rol(RolUsuario.CONSTRUCTOR))


class ColumnaSalida(BaseModel):
    nombre: str
    nombre_origen: str | None
    tipo: str
    nulos: int
    invalidos: int
    detalle: dict[str, Any] = {}


class FuenteSalida(BaseModel):
    id: int
    nombre: str
    nombre_tabla: str
    archivo_origen: str
    hoja: str | None
    formato: str
    huella: str
    filas: int
    estado: EstadoFuente
    error: str | None
    columnas: list[ColumnaSalida]
    opciones: dict[str, Any]
    creada_en: datetime
    actualizada_en: datetime


class MuestraSalida(BaseModel):
    columnas: list[str]
    tipos: list[str]
    filas: list[list[Any]]
    total: int


def a_fuente_salida(fuente: Fuente) -> FuenteSalida:
    return FuenteSalida(
        id=fuente.id,
        nombre=fuente.nombre,
        nombre_tabla=fuente.nombre_tabla,
        archivo_origen=fuente.archivo_origen,
        hoja=fuente.hoja,
        formato=fuente.formato,
        huella=fuente.huella,
        filas=fuente.filas,
        estado=fuente.estado,
        error=fuente.error,
        columnas=[ColumnaSalida(**columna) for columna in fuente.esquema],
        opciones=fuente.opciones or {},
        creada_en=fuente.creada_en,
        actualizada_en=fuente.actualizada_en,
    )


def fuente_del_workspace(
    fuente_id: int,
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
) -> Fuente:
    fuente = sesion.scalar(select(Fuente).where(Fuente.id == fuente_id, Fuente.workspace_id == workspace.id))
    if fuente is None:
        raise ErrorApp("E-ING-04", f"id: {fuente_id}")
    return fuente


@router.get("", response_model=list[FuenteSalida])
def listar_fuentes(
    workspace: Workspace = Depends(workspace_del_usuario), sesion: Session = Depends(obtener_sesion)
) -> list[FuenteSalida]:
    fuentes = sesion.scalars(select(Fuente).where(Fuente.workspace_id == workspace.id).order_by(Fuente.nombre_tabla)).all()
    return [a_fuente_salida(fuente) for fuente in fuentes]


@router.post("", response_model=list[TareaSalida], status_code=status.HTTP_202_ACCEPTED)
async def subir_archivos(
    archivos: list[UploadFile] = File(..., description="Uno o mas CSV / Excel"),
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
    almacen: AlmacenArchivos = Depends(obtener_almacen),
    cola: ColaTareas = Depends(obtener_cola),
) -> list[TareaSalida]:
    """Guarda cada archivo tal cual en el almacen y encola una tarea de ingesta
    por archivo. Responde 202 con las tareas: el frontend hace polling."""
    limite = obtener_configuracion().tamanio_maximo_archivo_mb * 1024 * 1024
    pendientes = []
    for archivo in archivos:
        nombre_archivo = archivo.filename or "archivo"
        validar_extension(nombre_archivo)
        contenido = await archivo.read()
        if len(contenido) > limite:
            raise ErrorApp("E-ING-02", f"{nombre_archivo}: {len(contenido)} bytes")
        if not contenido.strip():
            raise ErrorApp("E-ING-03", f"archivo: {nombre_archivo!r}")
        pendientes.append((nombre_archivo, contenido))

    tareas = []
    for nombre_archivo, contenido in pendientes:
        ruta_original = ruta_subida_original(workspace.organizacion_id, workspace.id, uuid.uuid4().hex, nombre_archivo)
        almacen.guardar(ruta_original, contenido)
        tarea = encolar_tarea(
            sesion,
            cola,
            tipo=TIPO_TAREA_INGESTA,
            parametros={"ruta_original": ruta_original, "nombre_archivo": nombre_archivo},
            workspace=workspace,
            usuario=usuario,
        )
        tareas.append(a_tarea_salida(tarea))
    return tareas


@router.get("/{fuente_id}", response_model=FuenteSalida)
def obtener_fuente(fuente: Fuente = Depends(fuente_del_workspace)) -> FuenteSalida:
    return a_fuente_salida(fuente)


@router.get("/{fuente_id}/muestra", response_model=MuestraSalida)
def muestra_de_fuente(
    fuente: Fuente = Depends(fuente_del_workspace),
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
    almacen: AlmacenArchivos = Depends(obtener_almacen),
    filas: int = Query(20, ge=1, le=500),
) -> MuestraSalida:
    conexion = obtener_motor().conexion(workspace.id, fuentes_listas(sesion, workspace), almacen)
    try:
        resultado = conexion.execute(f'SELECT * FROM "{fuente.nombre_tabla}" LIMIT {filas}')
        columnas = [descripcion[0] for descripcion in resultado.description]
        datos = [list(fila) for fila in resultado.fetchall()]
    finally:
        conexion.close()
    tipos = {columna["nombre"]: columna["tipo"] for columna in fuente.esquema}
    return MuestraSalida(columnas=columnas, tipos=[tipos.get(columna, "texto") for columna in columnas], filas=datos, total=fuente.filas)


@router.delete("/{fuente_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[solo_constructor])
def borrar_fuente(
    fuente: Fuente = Depends(fuente_del_workspace),
    sesion: Session = Depends(obtener_sesion),
    almacen: AlmacenArchivos = Depends(obtener_almacen),
) -> None:
    workspace_id = fuente.workspace_id
    eliminar_fuente(sesion, almacen, fuente)
    obtener_motor().invalidar(workspace_id)
