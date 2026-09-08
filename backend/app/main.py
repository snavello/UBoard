"""Punto de entrada de UBoard.

Un solo proceso sirve la API (bajo /api) y el frontend compilado por Vite
(backend/app/estatico/). En desarrollo el frontend lo sirve Vite en 5173 con
proxy a /api, y esta app solo expone la API.
"""
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import app.ingesta.tarea  # noqa: F401  registra el manejador de ingesta en la cola
from app.api import auth, fuentes, plataforma, salud, tareas, workspaces
from app.catalogo.sesion import nueva_sesion
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import registrar_manejadores
from app.tareas import marcar_tareas_huerfanas
from app.version import VERSION

RUTA_ESTATICO = Path(__file__).parent / "estatico"
SECRETO_POR_DEFECTO = "cambiar-este-secreto-en-produccion"
registro = logging.getLogger("uboard")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
    if obtener_configuracion().recuperar_tareas_al_arrancar:
        _recuperar_tareas()
    yield


def _recuperar_tareas() -> None:
    """Ninguna tarea sobrevive a un reinicio: lo que quedo corriendo se marca
    como error para que el frontend deje de esperarla. Si la base no responde
    al arrancar, se loguea y la app levanta igual."""
    sesion = nueva_sesion()
    try:
        cantidad = marcar_tareas_huerfanas(sesion)
        if cantidad:
            registro.warning("%d tarea(s) huerfana(s) marcadas como error al arrancar", cantidad)
    except Exception:  # noqa: BLE001
        registro.exception("No se pudieron revisar las tareas huerfanas al arrancar")
    finally:
        sesion.close()


def crear_app() -> FastAPI:
    _verificar_configuracion()

    app = FastAPI(
        title="UBoard",
        version=VERSION,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=ciclo_de_vida,
    )
    registrar_manejadores(app)

    app.include_router(salud.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(plataforma.router, prefix="/api")
    app.include_router(workspaces.router, prefix="/api")
    app.include_router(tareas.router, prefix="/api")
    app.include_router(fuentes.router, prefix="/api")

    _montar_frontend(app)
    return app


def _verificar_configuracion() -> None:
    """Fuera de local, arrancar con el secreto de ejemplo es un error de
    despliegue: mejor que no levante."""
    configuracion = obtener_configuracion()
    if configuracion.entorno != "local" and configuracion.secreto_sesion == SECRETO_POR_DEFECTO:
        raise RuntimeError("SECRETO_SESION tiene el valor de ejemplo; definilo antes de arrancar fuera de local")


def _montar_frontend(app: FastAPI) -> None:
    """Sirve el build de Vite si existe. Los assets llevan hash en el nombre
    (cache larga sin riesgo); index.html se entrega para cualquier ruta que no
    sea de la API, asi el router de React resuelve la navegacion."""
    indice = RUTA_ESTATICO / "index.html"
    if not indice.exists():
        return

    app.mount("/assets", StaticFiles(directory=RUTA_ESTATICO / "assets"), name="assets")

    @app.get("/{ruta:path}", include_in_schema=False)
    def frontend(ruta: str) -> FileResponse:
        if ruta.startswith("api/"):
            raise HTTPException(status_code=404, detail="Ruta de API inexistente")
        archivo = RUTA_ESTATICO / ruta
        if ruta and archivo.is_file():
            return FileResponse(archivo)
        return FileResponse(indice, headers={"Cache-Control": "no-cache"})


app = crear_app()
