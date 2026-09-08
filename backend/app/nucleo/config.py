"""Configuracion de UBoard, leida de variables de entorno o del .env de la raiz.

Se valida al arrancar: si falta algo o tiene un tipo invalido, la app no
levanta, en vez de fallar horas despues en un request.
"""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/nucleo/config.py -> raiz del repo (donde viven .env y datos/)
RAIZ_PROYECTO = Path(__file__).resolve().parents[3]


class Configuracion(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Catalogo en Postgres (SQLAlchemy + psycopg 3)
    database_url: str = "postgresql+psycopg://uboard:uboard-dev-local@localhost:5433/uboard_dev"
    # Base aparte para los tests de API; nunca la misma que database_url
    database_url_test: str = "postgresql+psycopg://uboard:uboard-dev-local@localhost:5433/uboard_test"

    # Sesion: JWT firmado con este secreto, vence por inactividad
    secreto_sesion: str = "cambiar-este-secreto-en-produccion"
    minutos_inactividad: int = 15

    # Almacen local de archivos (Parquet y subidas)
    ruta_almacen: Path = RAIZ_PROYECTO / "datos" / "almacen"

    # local | pruebas | demo | prod
    entorno: str = "local"

    @field_validator("ruta_almacen")
    @classmethod
    def _ruta_absoluta(cls, valor: Path) -> Path:
        """Una ruta relativa en el .env se toma desde la raiz del repo, no desde
        el directorio donde se lanzo uvicorn."""
        return valor if valor.is_absolute() else RAIZ_PROYECTO / valor

    @property
    def muestra_distintivo(self) -> bool:
        """En local y pruebas la UI muestra entorno + version para no confundir
        pantallas en una presentacion."""
        return self.entorno in ("local", "pruebas")


@lru_cache
def obtener_configuracion() -> Configuracion:
    return Configuracion()
