"""Perfil de una tabla DuckDB: por columna, nulos, distintos, minimo, maximo,
promedio, largos, valores frecuentes y patron de texto; por tabla, filas y
candidatas a clave. Puro: recibe una conexion y la relacion a leer, no toca
el catalogo. Los valores salen listos para JSON (fechas ISO, decimales como
float).
"""
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from app.ingesta.tipado import columna_sql

CANTIDAD_TOP_VALORES = 10
# Cuantos valores distintos se miran para decidir el patron de una columna de texto
MUESTRA_PATRON = 200

TIPOS_NUMERICOS = {"entero", "decimal"}
TIPOS_TEMPORALES = {"fecha", "fecha_hora"}

# Patrones de texto, del mas especifico al mas general. Cada uno se adopta si
# lo cumplen al menos el 90 % de los valores distintos muestreados.
PATRONES: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")),
    ("url", re.compile(r"^https?://\S+$", re.IGNORECASE)),
    ("numerico", re.compile(r"^\d+$")),
    ("codigo", re.compile(r"^(?=.*\d)[A-Za-z0-9._/-]+$")),
]
UMBRAL_PATRON = 0.9


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TopValor(_Base):
    valor: Any
    cantidad: int


class PerfilColumna(_Base):
    nombre: str
    tipo: str
    nulos: int
    distintos: int
    # Sin nulos y todos los valores distintos: candidata a clave
    unica: bool
    minimo: Any = None
    maximo: Any = None
    promedio: float | None = None
    longitud_minima: int | None = None
    longitud_maxima: int | None = None
    top_valores: list[TopValor] = Field(default_factory=list)
    # email | url | numerico | codigo | None (solo columnas de texto)
    patron: str | None = None


class PerfilFuente(_Base):
    nombre_tabla: str
    filas: int
    columnas: list[PerfilColumna]
    candidatas_clave: list[str]

    def columna(self, nombre: str) -> PerfilColumna | None:
        return next((columna for columna in self.columnas if columna.nombre == nombre), None)


def _a_json(valor: Any) -> Any:
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return valor


def _detectar_patron(valores: list[str]) -> str | None:
    if not valores:
        return None
    for nombre, patron in PATRONES:
        coincidencias = sum(1 for valor in valores if patron.match(valor))
        if coincidencias / len(valores) >= UMBRAL_PATRON:
            return nombre
    return None


def perfilar(
    conexion: duckdb.DuckDBPyConnection, relacion: str, nombre_tabla: str, columnas: list[tuple[str, str]]
) -> PerfilFuente:
    """`relacion` es lo que va despues del FROM (una vista, o
    `read_parquet('...')`); `columnas` = [(nombre, tipo)] del esquema de la
    fuente. Una pasada de agregados para todas las columnas y una consulta
    chica por columna para los valores frecuentes."""
    filas = conexion.execute(f"SELECT count(*) FROM {relacion}").fetchone()[0]

    agregados: list[str] = []
    for nombre, tipo in columnas:
        columna = columna_sql(nombre)
        agregados.append(f"count({columna})")
        agregados.append(f"count(DISTINCT {columna})")
        if tipo in TIPOS_NUMERICOS or tipo in TIPOS_TEMPORALES:
            agregados.append(f"min({columna})")
            agregados.append(f"max({columna})")
        else:
            agregados.append("NULL")
            agregados.append("NULL")
        agregados.append(f"avg({columna})" if tipo in TIPOS_NUMERICOS else "NULL")
        if tipo == "texto":
            agregados.append(f"min(length(CAST({columna} AS VARCHAR)))")
            agregados.append(f"max(length(CAST({columna} AS VARCHAR)))")
        else:
            agregados.append("NULL")
            agregados.append("NULL")
    valores = conexion.execute(f"SELECT {', '.join(agregados)} FROM {relacion}").fetchone() if columnas else ()

    perfiles: list[PerfilColumna] = []
    for posicion, (nombre, tipo) in enumerate(columnas):
        base = posicion * 7
        no_nulos, distintos, minimo, maximo, promedio, largo_min, largo_max = valores[base : base + 7]
        columna = columna_sql(nombre)
        top = conexion.execute(
            f"SELECT {columna}, count(*) AS cantidad FROM {relacion} WHERE {columna} IS NOT NULL "
            f"GROUP BY {columna} ORDER BY cantidad DESC, {columna} LIMIT {CANTIDAD_TOP_VALORES}"
        ).fetchall()
        patron = None
        if tipo == "texto":
            muestra = conexion.execute(
                f"SELECT DISTINCT {columna} FROM {relacion} WHERE {columna} IS NOT NULL LIMIT {MUESTRA_PATRON}"
            ).fetchall()
            patron = _detectar_patron([str(fila[0]) for fila in muestra])
        perfiles.append(
            PerfilColumna(
                nombre=nombre,
                tipo=tipo,
                nulos=filas - no_nulos,
                distintos=distintos,
                unica=filas > 0 and no_nulos == filas and distintos == filas,
                minimo=_a_json(minimo),
                maximo=_a_json(maximo),
                promedio=float(promedio) if promedio is not None else None,
                longitud_minima=largo_min,
                longitud_maxima=largo_max,
                top_valores=[TopValor(valor=_a_json(valor), cantidad=cantidad) for valor, cantidad in top],
                patron=patron,
            )
        )

    # Candidatas a clave: unicas, y de un tipo que sirve como identificador
    candidatas = [perfil.nombre for perfil in perfiles if perfil.unica and perfil.tipo in ("entero", "texto")]
    return PerfilFuente(nombre_tabla=nombre_tabla, filas=filas, columnas=perfiles, candidatas_clave=candidatas)
