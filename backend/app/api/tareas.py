"""Estado de las tareas de un workspace, para el polling del frontend."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.workspaces import workspace_del_usuario
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import EstadoTarea, Tarea, Workspace
from app.nucleo.errores import ErrorApp
from app.tareas.cola import tareas_del_workspace

router = APIRouter(prefix="/workspaces/{workspace_id}/tareas", tags=["tareas"])


class TareaSalida(BaseModel):
    id: str
    tipo: str
    estado: EstadoTarea
    progreso: int
    mensaje: str | None
    resultado: dict[str, Any] | None
    error: str | None
    creada_en: datetime
    iniciada_en: datetime | None
    terminada_en: datetime | None


def a_tarea_salida(tarea: Tarea) -> TareaSalida:
    return TareaSalida(
        id=tarea.id,
        tipo=tarea.tipo,
        estado=tarea.estado,
        progreso=tarea.progreso,
        mensaje=tarea.mensaje,
        resultado=tarea.resultado,
        error=tarea.error,
        creada_en=tarea.creada_en,
        iniciada_en=tarea.iniciada_en,
        terminada_en=tarea.terminada_en,
    )


def tarea_del_workspace(
    tarea_id: str,
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
) -> Tarea:
    """La tarea se busca dentro del workspace ya autorizado: una de otro
    workspace no existe para este usuario."""
    tarea = sesion.scalar(select(Tarea).where(Tarea.id == tarea_id, Tarea.workspace_id == workspace.id))
    if tarea is None:
        raise ErrorApp("E-TAREA-01", f"id: {tarea_id}")
    return tarea


@router.get("", response_model=list[TareaSalida])
def listar_tareas(
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
    limite: int = Query(20, ge=1, le=200),
) -> list[TareaSalida]:
    return [a_tarea_salida(tarea) for tarea in tareas_del_workspace(sesion, workspace, limite)]


@router.get("/{tarea_id}", response_model=TareaSalida)
def obtener_tarea(tarea: Tarea = Depends(tarea_del_workspace)) -> TareaSalida:
    return a_tarea_salida(tarea)
