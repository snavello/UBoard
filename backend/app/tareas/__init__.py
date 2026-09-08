"""Tareas en segundo plano detras de una interfaz.

- `registrar_tarea("area.accion")` decora la funcion que hace el trabajo.
- `encolar_tarea(...)` crea la fila en `tarea` y la manda a la cola.
- `ColaLocal` (unica implementacion hoy) la corre en un hilo del mismo
  proceso. Un worker con Redis, mas adelante, implementa la misma interfaz.
- El frontend sigue el progreso por polling sobre GET .../tareas/{id}.
"""
from app.tareas.cola import (
    ColaLocal,
    ColaTareas,
    ContextoTarea,
    encolar_tarea,
    marcar_tareas_huerfanas,
    obtener_cola,
)
from app.tareas.registro import obtener_manejador, registrar_tarea

__all__ = [
    "ColaLocal",
    "ColaTareas",
    "ContextoTarea",
    "encolar_tarea",
    "marcar_tareas_huerfanas",
    "obtener_cola",
    "obtener_manejador",
    "registrar_tarea",
]
