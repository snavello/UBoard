"""Engine y sesiones de SQLAlchemy para el catalogo."""
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.nucleo.config import obtener_configuracion


@lru_cache
def obtener_engine() -> Engine:
    configuracion = obtener_configuracion()
    # pool_pre_ping: si Postgres reinicio o cerro la conexion, se detecta antes
    # de usarla en vez de fallar el primer request.
    return create_engine(configuracion.database_url, pool_pre_ping=True)


@lru_cache
def _fabrica_sesiones() -> sessionmaker[Session]:
    return sessionmaker(bind=obtener_engine(), autoflush=False, expire_on_commit=False)


def obtener_sesion() -> Generator[Session, None, None]:
    """Dependencia de FastAPI: una sesion por request, cerrada al terminar."""
    sesion = _fabrica_sesiones()()
    try:
        yield sesion
    finally:
        sesion.close()
