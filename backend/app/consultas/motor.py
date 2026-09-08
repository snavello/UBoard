"""Una base DuckDB en memoria por workspace, con una VISTA por fuente sobre su
Parquet. Se reconstruye cuando cambia el conjunto de fuentes (firma) o cuando
alguien la invalida; asi resubir una fuente es reemplazar el Parquet y no
hay archivo .duckdb que administrar ni bloquear entre procesos.
"""
import threading

import duckdb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.almacen.base import AlmacenArchivos
from app.catalogo.tablas import EstadoFuente, Fuente, Workspace


def fuentes_listas(sesion: Session, workspace: Workspace) -> list[Fuente]:
    return list(
        sesion.scalars(
            select(Fuente)
            .where(Fuente.workspace_id == workspace.id, Fuente.estado == EstadoFuente.LISTA)
            .order_by(Fuente.nombre_tabla)
        )
    )


def _firma(fuentes: list[Fuente]) -> str:
    return "|".join(f"{fuente.nombre_tabla}:{fuente.huella}:{fuente.ruta_parquet}:{fuente.actualizada_en}" for fuente in fuentes)


class MotorWorkspace:
    def __init__(self) -> None:
        self._bases: dict[int, tuple[str, duckdb.DuckDBPyConnection]] = {}
        self._candado = threading.Lock()

    def conexion(self, workspace_id: int, fuentes: list[Fuente], almacen: AlmacenArchivos) -> duckdb.DuckDBPyConnection:
        """Cursor propio para el llamador (DuckDB no comparte una conexion entre
        hilos). Cerrarlo al terminar."""
        firma = _firma(fuentes)
        with self._candado:
            entrada = self._bases.get(workspace_id)
            if entrada is None or entrada[0] != firma:
                if entrada is not None:
                    entrada[1].close()
                base = duckdb.connect()
                for fuente in fuentes:
                    uri = almacen.uri_para_duckdb(fuente.ruta_parquet).replace("'", "''")
                    base.execute(f'CREATE OR REPLACE VIEW "{fuente.nombre_tabla}" AS SELECT * FROM read_parquet(\'{uri}\')')
                self._bases[workspace_id] = (firma, base)
                entrada = self._bases[workspace_id]
            return entrada[1].cursor()

    def invalidar(self, workspace_id: int) -> None:
        with self._candado:
            entrada = self._bases.pop(workspace_id, None)
            if entrada is not None:
                entrada[1].close()


_motor = MotorWorkspace()


def obtener_motor() -> MotorWorkspace:
    return _motor
