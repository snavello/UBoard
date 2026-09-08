"""Ejecuta una consulta semantica sobre el DuckDB del workspace y devuelve una
tabla tipada, lista para serializar."""
from dataclasses import dataclass
from typing import Any

import duckdb
from sqlalchemy.orm import Session

from app.almacen.base import AlmacenArchivos
from app.catalogo.tablas import Workspace
from app.consultas.compilador import ColumnaResultado, SQLCompilado, compilar
from app.consultas.esquema import ConsultaSemantica
from app.consultas.motor import fuentes_listas, obtener_motor
from app.modelo.esquema import ModeloSemantico
from app.nucleo.errores import ErrorApp


@dataclass
class ResultadoConsulta:
    columnas: list[ColumnaResultado]
    filas: list[list[Any]]
    sql: str

    def como_dict(self) -> dict[str, Any]:
        return {
            "columnas": [
                {"nombre": c.nombre, "tipo": c.tipo, "clase": c.clase, "granularidad": c.granularidad} for c in self.columnas
            ],
            "filas": self.filas,
        }


def ejecutar_compilada(conexion: duckdb.DuckDBPyConnection, compilada: SQLCompilado) -> ResultadoConsulta:
    try:
        filas = conexion.execute(compilada.sql, compilada.parametros).fetchall()
    except duckdb.Error as error:
        # Si llegamos aca con un modelo validado, es un bug del compilador o un
        # Parquet que cambio por debajo: se informa con el SQL para depurar.
        raise ErrorApp("E-CONS-09", f"{type(error).__name__}: {str(error).splitlines()[0]} | SQL: {compilada.sql}") from error
    return ResultadoConsulta(compilada.columnas, [list(fila) for fila in filas], compilada.sql)


def consultar(
    sesion: Session,
    workspace: Workspace,
    almacen: AlmacenArchivos,
    modelo: ModeloSemantico,
    consulta: ConsultaSemantica,
) -> ResultadoConsulta:
    """Compila contra el modelo (efectivo) y ejecuta en el DuckDB del workspace."""
    compilada = compilar(modelo, consulta)
    conexion = obtener_motor().conexion(workspace.id, fuentes_listas(sesion, workspace), almacen)
    try:
        return ejecutar_compilada(conexion, compilada)
    finally:
        conexion.close()
