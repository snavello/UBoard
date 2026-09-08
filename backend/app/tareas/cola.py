"""Cola de tareas: interfaz y la implementacion local (hilo en el proceso)."""
from __future__ import annotations

import logging
import secrets
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.catalogo.sesion import nueva_sesion
from app.catalogo.tablas import EstadoTarea, Tarea, Usuario, Workspace
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp
from app.tareas.registro import obtener_manejador

registro = logging.getLogger("uboard.tareas")

MENSAJE_HUERFANA = "El servidor se reinició mientras corría. Volvé a intentarlo."


@dataclass
class ContextoTarea:
    """Lo que ve un manejador mientras corre."""

    sesion: Session
    tarea: Tarea

    @property
    def workspace_id(self) -> int | None:
        return self.tarea.workspace_id

    def informar(self, progreso: int, mensaje: str | None = None) -> None:
        """Deja el avance en la fila para que el polling lo vea enseguida."""
        self.tarea.progreso = max(0, min(100, int(progreso)))
        if mensaje is not None:
            self.tarea.mensaje = mensaje[:300]
        self.sesion.commit()


class ColaTareas(ABC):
    @abstractmethod
    def encolar(self, tarea_id: str) -> None:
        """Manda a correr una tarea que YA existe en la base (estado pendiente)."""

    @abstractmethod
    def esperar(self, tarea_id: str, timeout: float | None = None) -> None:
        """Bloquea hasta que la tarea termine (para tests y scripts)."""


class ColaLocal(ColaTareas):
    """Un ThreadPoolExecutor en el mismo proceso. Con 1 hilo las tareas de un
    servidor corren de a una, en orden: alcanza para archivos chicos y evita
    dos ingestas pisandose. Cada tarea abre su propia sesion de base."""

    def __init__(self, fabrica_sesiones: Callable[[], Session] = nueva_sesion, hilos: int = 1):
        self._fabrica_sesiones = fabrica_sesiones
        self._ejecutor = ThreadPoolExecutor(max_workers=hilos, thread_name_prefix="tarea")
        self._futuros: dict[str, Future] = {}

    def encolar(self, tarea_id: str) -> None:
        self._futuros[tarea_id] = self._ejecutor.submit(self._correr, tarea_id)

    def esperar(self, tarea_id: str, timeout: float | None = None) -> None:
        futuro = self._futuros.get(tarea_id)
        if futuro is not None:
            futuro.result(timeout=timeout)

    def cerrar(self) -> None:
        self._ejecutor.shutdown(wait=True)

    def _correr(self, tarea_id: str) -> None:
        sesion = self._fabrica_sesiones()
        try:
            tarea = sesion.get(Tarea, tarea_id)
            if tarea is None:
                registro.error("Tarea %s encolada pero inexistente en la base", tarea_id)
                return
            tarea.estado = EstadoTarea.CORRIENDO
            tarea.iniciada_en = datetime.now(timezone.utc)
            sesion.commit()
            try:
                manejador = obtener_manejador(tarea.tipo)
                resultado = manejador(ContextoTarea(sesion, tarea), dict(tarea.parametros or {}))
            except ErrorApp as error:
                sesion.rollback()
                _terminar(sesion, tarea, error=f"{error.codigo}: {error.mensaje}" + (f" ({error.detalle})" if error.detalle else ""))
                return
            except Exception as error:  # noqa: BLE001  una tarea rota no tumba el hilo
                sesion.rollback()
                ref = secrets.token_hex(4)
                registro.error("Tarea %s (%s) fallo ref=%s\n%s", tarea_id, tarea.tipo, ref, "".join(traceback.format_exception(error)))
                _terminar(sesion, tarea, error=f"E-INTERNO-00 ref={ref}: {type(error).__name__}")
                return
            _terminar(sesion, tarea, resultado=resultado)
        finally:
            sesion.close()


def _terminar(sesion: Session, tarea: Tarea, *, resultado: dict[str, Any] | None = None, error: str | None = None) -> None:
    tarea.terminada_en = datetime.now(timezone.utc)
    if error is not None:
        tarea.estado = EstadoTarea.ERROR
        tarea.error = error
    else:
        tarea.estado = EstadoTarea.TERMINADA
        tarea.progreso = 100
        tarea.resultado = resultado
    sesion.commit()


def encolar_tarea(
    sesion: Session,
    cola: ColaTareas,
    *,
    tipo: str,
    parametros: dict[str, Any] | None = None,
    workspace: Workspace | None = None,
    usuario: Usuario | None = None,
) -> Tarea:
    """Crea la fila (commit) y despues la encola: el hilo tiene que poder
    leerla. Devuelve la tarea en estado pendiente; el llamador responde con su
    id y el frontend hace polling."""
    obtener_manejador(tipo)  # falla antes de crear la fila si el tipo no existe
    tarea = Tarea(
        tipo=tipo,
        parametros=parametros or {},
        workspace_id=workspace.id if workspace else None,
        creada_por_id=usuario.id if usuario else None,
    )
    sesion.add(tarea)
    sesion.commit()
    sesion.refresh(tarea)  # carga creada_en y demas defaults del servidor
    cola.encolar(tarea.id)
    return tarea


def marcar_tareas_huerfanas(sesion: Session) -> int:
    """Al arrancar el servidor: lo que quedo pendiente o corriendo pertenece a
    un proceso que ya no existe. Se marca como error para que nadie lo espere
    para siempre. Devuelve cuantas marco."""
    ahora = datetime.now(timezone.utc)
    resultado = sesion.execute(
        update(Tarea)
        .where(Tarea.estado.in_([EstadoTarea.PENDIENTE, EstadoTarea.CORRIENDO]))
        .values(estado=EstadoTarea.ERROR, error=f"E-TAREA-03: {MENSAJE_HUERFANA}", terminada_en=ahora)
    )
    sesion.commit()
    return resultado.rowcount or 0


def tareas_del_workspace(sesion: Session, workspace: Workspace, limite: int = 20) -> list[Tarea]:
    return list(
        sesion.scalars(
            select(Tarea).where(Tarea.workspace_id == workspace.id).order_by(Tarea.creada_en.desc()).limit(limite)
        )
    )


@lru_cache
def obtener_cola() -> ColaTareas:
    """Dependencia de FastAPI. En tests se reemplaza por una ColaLocal con la
    fabrica de sesiones de la base de tests."""
    return ColaLocal(hilos=obtener_configuracion().hilos_tareas)
