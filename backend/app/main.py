"""Punto de entrada de UBoard.

Un solo proceso sirve la API (bajo /api) y el frontend compilado por Vite
(backend/app/estatico/). En desarrollo el frontend lo sirve Vite en 5173 con
proxy a /api, y esta app solo expone la API.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import salud
from app.version import VERSION

RUTA_ESTATICO = Path(__file__).parent / "estatico"


def crear_app() -> FastAPI:
    app = FastAPI(title="UBoard", version=VERSION, docs_url="/api/docs", openapi_url="/api/openapi.json")

    app.include_router(salud.router, prefix="/api")

    _montar_frontend(app)
    return app


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
