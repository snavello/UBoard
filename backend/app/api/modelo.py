"""Modelo semantico de un workspace: cargar (constructor), validar sin guardar,
leer la version actual (completa o efectiva) y el historial de versiones."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.tareas import TareaSalida, a_tarea_salida
from app.api.workspaces import workspace_del_usuario
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import RolUsuario, Usuario, VersionModelo, Workspace
from app.inferencia.tarea import TIPO_TAREA_PROPONER_MODELO
from app.modelo import operaciones
from app.modelo.validacion import modelo_efectivo, parsear_modelo, validar_contra_fuentes, validar_estructura
from app.nucleo.auth import exigir_rol
from app.nucleo.errores import ErrorApp
from app.tareas import ColaTareas, encolar_tarea, obtener_cola

router = APIRouter(prefix="/workspaces/{workspace_id}/modelo", tags=["modelo"])


class VersionResumen(BaseModel):
    numero: int
    operacion: str
    resumen: str | None
    autor_id: int | None
    creada_en: datetime
    diff: dict[str, Any] | None


class VersionSalida(VersionResumen):
    contenido: dict[str, Any]


class ResultadoValidacion(BaseModel):
    valido: bool
    errores: list[dict[str, str]]
    resumen: str | None = None


def _resumen(version: VersionModelo) -> VersionResumen:
    return VersionResumen(
        numero=version.numero,
        operacion=version.operacion,
        resumen=version.resumen,
        autor_id=version.autor_id,
        creada_en=version.creada_en,
        diff=version.diff,
    )


def _salida(version: VersionModelo, efectivo: bool = False) -> VersionSalida:
    contenido = version.contenido
    if efectivo:
        contenido = modelo_efectivo(operaciones.modelo_de(version)).model_dump(mode="json")
    return VersionSalida(**_resumen(version).model_dump(), contenido=contenido)


@router.get("", response_model=VersionSalida)
def modelo_actual(
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
    efectivo: bool = Query(False, description="Solo lo confirmado o con confianza >= umbral"),
) -> VersionSalida:
    return _salida(operaciones.exigir_version_actual(sesion, workspace), efectivo)


@router.put("", response_model=VersionSalida, status_code=status.HTTP_201_CREATED)
def cargar_modelo(
    contenido: dict[str, Any] = Body(...),
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
) -> VersionSalida:
    """Reemplaza el modelo entero: valida las tres capas y crea una version nueva."""
    return _salida(operaciones.cargar_modelo(sesion, workspace, contenido, usuario))


@router.post("/validar", response_model=ResultadoValidacion, dependencies=[Depends(exigir_rol(RolUsuario.CONSTRUCTOR))])
def validar_modelo(
    contenido: dict[str, Any] = Body(...),
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
) -> ResultadoValidacion:
    """Misma validacion que la carga, sin guardar: para probar el JSON antes."""
    try:
        modelo = parsear_modelo(contenido)
    except ErrorApp as error:
        return ResultadoValidacion(valido=False, errores=(error.extra or {}).get("errores", []))
    errores = validar_estructura(modelo)
    if not errores:
        errores = validar_contra_fuentes(modelo, operaciones.esquemas_del_workspace(sesion, workspace))
    return ResultadoValidacion(valido=not errores, errores=[error.como_dict() for error in errores], resumen=modelo.resumen())


@router.get("/operaciones", response_model=list[str])
def listar_operaciones() -> list[str]:
    """Nombres de las operaciones granulares disponibles (§4)."""
    from app.modelo.edicion import OPERACIONES

    return list(OPERACIONES)


@router.post("/operaciones", response_model=VersionSalida, status_code=status.HTTP_201_CREATED)
def aplicar_operacion(
    contenido: dict[str, Any] = Body(..., description='{"operacion": "renombrar_campo", ...parametros}'),
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
) -> VersionSalida:
    """Una operacion granular (wizard o chat): valida, aplica sobre la version
    actual y crea una version nueva. E-MOD-04 si la operacion no existe,
    E-MOD-05 si no se puede aplicar, E-MOD-01 si el modelo resultante no valida."""
    return _salida(operaciones.aplicar_y_guardar(sesion, workspace, contenido, usuario))


@router.post("/proponer", response_model=TareaSalida, status_code=status.HTTP_202_ACCEPTED)
def proponer_modelo(
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
    cola: ColaTareas = Depends(obtener_cola),
) -> TareaSalida:
    """Encola la inferencia heuristica (fase 2): claves, relaciones, tipos
    semanticos, metricas obvias. Se fusiona con el modelo actual respetando
    lo confirmado y lo rechazado, y crea una version nueva. 202 + tarea."""
    tarea = encolar_tarea(sesion, cola, tipo=TIPO_TAREA_PROPONER_MODELO, parametros={}, workspace=workspace, usuario=usuario)
    return a_tarea_salida(tarea)


@router.get("/versiones", response_model=list[VersionResumen])
def listar_versiones(
    workspace: Workspace = Depends(workspace_del_usuario), sesion: Session = Depends(obtener_sesion)
) -> list[VersionResumen]:
    return [_resumen(version) for version in operaciones.listar_versiones(sesion, workspace)]


@router.get("/versiones/{numero}", response_model=VersionSalida)
def obtener_version(
    numero: int, workspace: Workspace = Depends(workspace_del_usuario), sesion: Session = Depends(obtener_sesion)
) -> VersionSalida:
    return _salida(operaciones.obtener_version(sesion, workspace, numero))


@router.post("/versiones/{numero}/restaurar", response_model=VersionSalida, status_code=status.HTTP_201_CREATED)
def restaurar_version(
    numero: int,
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
) -> VersionSalida:
    """Deshacer (paso 17): vuelve a guardar el contenido de la versión
    `numero` como una versión nueva. "Deshacer el último cambio" es
    restaurar la versión anterior a la actual; se puede restaurar
    cualquier otra para volver más atrás. E-MOD-03 si no existe."""
    return _salida(operaciones.restaurar(sesion, workspace, numero, usuario))
