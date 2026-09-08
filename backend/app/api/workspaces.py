"""Workspaces del usuario. Aca vive `workspace_del_usuario`, la dependencia
que todas las rutas de datos (fuentes, modelo, dashboard) van a usar para
resolver `/workspaces/{workspace_id}/...` SIN cruzar organizaciones: el
workspace se busca siempre dentro de la organizacion del usuario logueado,
nunca por id suelto."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.esquemas import WorkspaceSalida, a_workspace_salida
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import Usuario, Workspace
from app.nucleo.auth import usuario_actual
from app.nucleo.errores import ErrorApp

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def workspace_del_usuario(
    workspace_id: int,
    usuario: Usuario = Depends(usuario_actual),
    sesion: Session = Depends(obtener_sesion),
) -> Workspace:
    """404 si el workspace no existe O si es de otra organizacion: desde afuera
    no se distingue, y asi no se puede enumerar ids ajenos."""
    if usuario.organizacion_id is None:
        raise ErrorApp("E-WS-01", f"id: {workspace_id}")
    workspace = sesion.scalar(
        select(Workspace).where(Workspace.id == workspace_id, Workspace.organizacion_id == usuario.organizacion_id)
    )
    if workspace is None:
        raise ErrorApp("E-WS-01", f"id: {workspace_id}")
    return workspace


@router.get("", response_model=list[WorkspaceSalida])
def listar_workspaces(
    usuario: Usuario = Depends(usuario_actual), sesion: Session = Depends(obtener_sesion)
) -> list[WorkspaceSalida]:
    if usuario.organizacion_id is None:
        return []
    workspaces = sesion.scalars(
        select(Workspace).where(Workspace.organizacion_id == usuario.organizacion_id).order_by(Workspace.id)
    ).all()
    return [a_workspace_salida(workspace) for workspace in workspaces]


@router.get("/{workspace_id}", response_model=WorkspaceSalida)
def obtener_workspace(workspace: Workspace = Depends(workspace_del_usuario)) -> WorkspaceSalida:
    return a_workspace_salida(workspace)
