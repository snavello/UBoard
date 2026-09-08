"""Registro de manejadores de tarea: nombre -> funcion.

Un manejador recibe el contexto (sesion propia del hilo, la fila de la tarea,
`informar(progreso, mensaje)`) y los parametros guardados en la fila, y
devuelve un dict que queda en `tarea.resultado`.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.nucleo.errores import ErrorApp

if TYPE_CHECKING:
    from app.tareas.cola import ContextoTarea

Manejador = Callable[["ContextoTarea", dict[str, Any]], dict[str, Any] | None]

_MANEJADORES: dict[str, Manejador] = {}


def registrar_tarea(tipo: str) -> Callable[[Manejador], Manejador]:
    """Decorador. El tipo es "area.accion" (ej. "ingesta.procesar_fuente") y
    es lo que se guarda en la fila, asi que no se renombra a la ligera."""

    def decorador(funcion: Manejador) -> Manejador:
        if tipo in _MANEJADORES:
            raise ValueError(f"Ya hay un manejador registrado para la tarea {tipo!r}")
        _MANEJADORES[tipo] = funcion
        return funcion

    return decorador


def obtener_manejador(tipo: str) -> Manejador:
    try:
        return _MANEJADORES[tipo]
    except KeyError:
        raise ErrorApp("E-TAREA-02", f"tipo: {tipo!r}") from None


def tipos_registrados() -> list[str]:
    return sorted(_MANEJADORES)
