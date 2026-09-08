"""Almacen de archivos (Parquet de las fuentes y archivos subidos).

Todo pasa por la interfaz `AlmacenArchivos`; hoy la unica implementacion es
`AlmacenLocal` (disco). En la fase 4 se suma `AlmacenS3` (Cloudflare R2) sin
tocar a quien lo usa: los llamadores reciben el almacen por `obtener_almacen`.
"""
from functools import lru_cache

from app.almacen.base import AlmacenArchivos
from app.almacen.local import AlmacenLocal
from app.nucleo.config import obtener_configuracion

__all__ = ["AlmacenArchivos", "AlmacenLocal", "obtener_almacen"]


@lru_cache
def obtener_almacen() -> AlmacenArchivos:
    """Dependencia de FastAPI. En tests se reemplaza por un AlmacenLocal en
    un directorio temporal."""
    return AlmacenLocal(obtener_configuracion().ruta_almacen)
