"""CSV -> tabla DuckDB con todas las columnas VARCHAR y nombres normalizados."""
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

from app.ingesta.codificacion import decodificar
from app.ingesta.encabezado import (
    MAX_LINEAS_MUESTRA,
    detectar_delimitador,
    detectar_fila_encabezado,
    dividir,
    nombres_de_columnas,
)
from app.nucleo.errores import ErrorApp


@dataclass
class TablaCruda:
    """Una tabla ya cargada en la conexion, todo texto, lista para tipar."""

    nombre_relacion: str
    columnas: list[str]
    columnas_origen: list[str | None]
    opciones: dict = field(default_factory=dict)


def cargar_csv(
    conexion: duckdb.DuckDBPyConnection, datos: bytes, nombre_relacion: str, directorio_temporal: Path
) -> TablaCruda:
    texto, encoding = decodificar(datos)
    lineas = texto.splitlines()
    if not any(linea.strip() for linea in lineas):
        raise ErrorApp("E-ING-03")

    muestra = lineas[:MAX_LINEAS_MUESTRA]
    delimitador = detectar_delimitador(muestra)
    filas_muestra = [dividir(linea, delimitador) for linea in muestra]
    indice, tiene_encabezado = detectar_fila_encabezado(filas_muestra)
    if indice is None:
        raise ErrorApp("E-ING-03")

    fila_encabezado = filas_muestra[indice]
    ancho = max(len(fila) for fila in filas_muestra[indice:]) or len(fila_encabezado)
    if tiene_encabezado:
        origen: list[str | None] = list(fila_encabezado) + [None] * (ancho - len(fila_encabezado))
    else:
        origen = [None] * ancho
    columnas = nombres_de_columnas(origen)

    # DuckDB lee UTF-8: se reescribe el texto ya decodificado, sin BOM
    ruta_temporal = directorio_temporal / f"{nombre_relacion}.csv"
    ruta_temporal.write_text("\n".join(lineas) + "\n", encoding="utf-8", newline="\n")
    saltar = indice + (1 if tiene_encabezado else 0)
    # Sin sniffer (auto_detect = false): ya sabemos delimitador, encabezado y
    # columnas, y el sniffer de DuckDB falla con filas de distinto largo. Con
    # strict_mode = false + null_padding, las filas cortas se rellenan con
    # NULL y las largas pierden las celdas sobrantes, sin descartar la fila.
    columnas_sql = "{" + ", ".join(f"'{columna}': 'VARCHAR'" for columna in columnas) + "}"
    opciones_lectura = (
        f"delim = ?, header = false, skip = ?, columns = {columnas_sql}, auto_detect = false, "
        "null_padding = true, strict_mode = false, quote = '\"', escape = '\"'"
    )
    errores_ignorados = False
    try:
        conexion.execute(
            f"CREATE OR REPLACE TABLE {nombre_relacion} AS SELECT * FROM read_csv(?, {opciones_lectura})",
            [str(ruta_temporal), delimitador, saltar],
        )
    except duckdb.Error:
        # Ultimo recurso: filas que no se pueden interpretar se descartan
        errores_ignorados = True
        conexion.execute(
            f"CREATE OR REPLACE TABLE {nombre_relacion} AS SELECT * FROM read_csv(?, {opciones_lectura}, ignore_errors = true)",
            [str(ruta_temporal), delimitador, saltar],
        )

    return TablaCruda(
        nombre_relacion=nombre_relacion,
        columnas=columnas,
        columnas_origen=origen,
        opciones={
            "codificacion": encoding,
            "delimitador": delimitador,
            "filas_saltadas": indice,
            "tiene_encabezado": tiene_encabezado,
            "errores_ignorados": errores_ignorados,
        },
    )
