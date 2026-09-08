"""Salud del backend: lo primero que consulta el frontend y lo que mira el
healthcheck del contenedor."""
from fastapi import APIRouter

from app.nucleo.config import obtener_configuracion
from app.version import FECHA_VERSION, VERSION

router = APIRouter(tags=["salud"])


@router.get("/salud")
def salud() -> dict:
    configuracion = obtener_configuracion()
    return {
        "estado": "ok",
        "version": VERSION,
        "fecha_version": FECHA_VERSION,
        "entorno": configuracion.entorno,
    }
