"""Texto sin delimitador estandar -> tabla DuckDB, aplicando una RECETA ya
confirmada (ancho fijo o regex). La receta la propone Claude
(app/inferencia/texto.py, con cache y reintento como el resto de la
inferencia); esta pieza es puramente deterministica: no sabe nada de Claude,
solo aplica una receta ya decidida, igual que un lector mas de la familia
(lector_csv.py, lector_excel.py).

`validar_receta` vive aca (no en inferencia) porque valida contra las
mismas reglas que despues va a ejecutar `cargar_texto_estructurado`, y la
necesitan tanto el reintento de Claude como, en el futuro, una edicion
manual de la receta antes de confirmar.
"""
import re
from pathlib import Path
from typing import Literal

import duckdb
import pyarrow
from pydantic import BaseModel, ConfigDict, Field

from app.ingesta.codificacion import decodificar
from app.ingesta.encabezado import nombres_de_columnas, normalizar_nombre_columna
from app.ingesta.lector_csv import TablaCruda
from app.nucleo.errores import ErrorApp

# Margen para el chequeo "las columnas cubren la linea": no hace falta llegar
# al 100% exacto (espacios finales que a veces se recortan en la muestra).
COBERTURA_MINIMA_ANCHO_FIJO = 0.8
# El patron regex tiene que matchear al menos esta fraccion de las lineas de
# muestra con contenido, si no la receta se rechaza y Claude reintenta.
COINCIDENCIA_MINIMA_REGEX = 0.5


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ColumnaReceta(_Base):
    nombre: str = Field(min_length=1, max_length=60)
    # Ancho fijo: posicion en la linea, 0-based, `fin` exclusivo. En modo
    # regex quedan en None: el orden de la lista ES el orden de los grupos
    # de captura del patron.
    inicio: int | None = Field(default=None, ge=0)
    fin: int | None = Field(default=None, ge=0)


class RecetaTexto(_Base):
    """Lo que propone Claude (o lo que la persona termina confirmando,
    eventualmente ajustado): como partir cada linea en columnas."""

    modo: Literal["ancho_fijo", "regex"]
    columnas: list[ColumnaReceta] = Field(min_length=1)
    patron: str | None = None  # obligatorio si modo == "regex"


def validar_receta(lineas_muestra: list[str], receta: RecetaTexto) -> list[str]:
    """Reglas que Pydantic no puede expresar solo: offsets sin solaparse que
    cubren la linea, o un regex que compila con un grupo por columna y
    matchea una fraccion razonable de la muestra. Devuelve una lista de
    strings en castellano (vacia si esta todo bien), nunca lanza excepcion:
    el llamador decide si reintenta o corta."""
    errores: list[str] = []
    # normalizar_nombre_columna directo (no nombres_de_columnas: esa ya
    # resuelve duplicados con sufijos, y acá justamente hace falta detectarlos).
    nombres_normalizados = [normalizar_nombre_columna(columna.nombre, posicion) for posicion, columna in enumerate(receta.columnas)]
    if len(set(nombres_normalizados)) != len(nombres_normalizados):
        errores.append("hay nombres de columna repetidos (una vez normalizados)")

    lineas_con_contenido = [linea for linea in lineas_muestra if linea.strip()]

    if receta.modo == "ancho_fijo":
        ordenadas = sorted(receta.columnas, key=lambda columna: columna.inicio if columna.inicio is not None else -1)
        fin_anterior = 0
        for columna in ordenadas:
            if columna.inicio is None or columna.fin is None:
                errores.append(f"la columna '{columna.nombre}' necesita inicio y fin (modo ancho_fijo)")
                continue
            if columna.fin <= columna.inicio:
                errores.append(f"la columna '{columna.nombre}' tiene fin <= inicio")
                continue
            if columna.inicio < fin_anterior:
                errores.append(f"la columna '{columna.nombre}' se solapa con la anterior")
            fin_anterior = max(fin_anterior, columna.fin)
        ancho_maximo = max((len(linea) for linea in lineas_con_contenido), default=0)
        if ancho_maximo > 0 and fin_anterior < ancho_maximo * COBERTURA_MINIMA_ANCHO_FIJO:
            errores.append(f"las columnas cubren hasta la posición {fin_anterior}, pero las líneas de muestra llegan hasta {ancho_maximo}")
    else:
        if not receta.patron:
            errores.append("falta el patrón regex (modo regex)")
            return errores
        try:
            compilado = re.compile(receta.patron)
        except re.error as error:
            errores.append(f"el patrón regex no compila: {error}")
            return errores
        if compilado.groups != len(receta.columnas):
            errores.append(f"el patrón tiene {compilado.groups} grupo(s) de captura pero hay {len(receta.columnas)} columna(s)")
        if lineas_con_contenido:
            coincidencias = sum(1 for linea in lineas_con_contenido if compilado.match(linea))
            proporcion = coincidencias / len(lineas_con_contenido)
            if proporcion < COINCIDENCIA_MINIMA_REGEX:
                errores.append(f"el patrón solo matchea {coincidencias} de {len(lineas_con_contenido)} línea(s) de muestra")
    return errores


def cargar_texto_estructurado(
    conexion: duckdb.DuckDBPyConnection,
    datos: bytes,
    nombre_relacion: str,
    receta: RecetaTexto,
    directorio_temporal: Path,  # no se usa (Arrow en memoria, como Excel); mismo shape que los demas lectores
) -> TablaCruda:
    """Aplica una receta YA CONFIRMADA, de forma deterministica, sobre TODO
    el archivo. Una linea que no matchea (regex) o queda corta (ancho fijo)
    nunca se descarta: sus columnas quedan NULL, igual que el resto de la
    ingesta cuenta un valor invalido en vez de tirar la fila."""
    texto, encoding = decodificar(datos)
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    if not lineas:
        raise ErrorApp("E-ING-03")

    nombres_origen: list[str | None] = [columna.nombre for columna in receta.columnas]
    columnas = nombres_de_columnas(nombres_origen)

    if receta.modo == "ancho_fijo":
        filas = [
            [((linea[columna.inicio : columna.fin] or "").strip() or None) for columna in receta.columnas]
            for linea in lineas
        ]
    else:
        patron = re.compile(receta.patron or "")
        filas = []
        for linea in lineas:
            coincidencia = patron.match(linea)
            if coincidencia is None:
                filas.append([None] * len(columnas))
            else:
                filas.append([(grupo.strip() or None) if grupo is not None else None for grupo in coincidencia.groups()])

    tabla_arrow = pyarrow.table(
        {columna: pyarrow.array([fila[posicion] for fila in filas], type=pyarrow.string()) for posicion, columna in enumerate(columnas)}
    )
    conexion.register(f"{nombre_relacion}_arrow", tabla_arrow)
    conexion.execute(f"CREATE OR REPLACE TABLE {nombre_relacion} AS SELECT * FROM {nombre_relacion}_arrow")
    conexion.unregister(f"{nombre_relacion}_arrow")

    return TablaCruda(
        nombre_relacion=nombre_relacion,
        columnas=columnas,
        columnas_origen=nombres_origen,
        opciones={"codificacion": encoding, "modo": receta.modo, "receta": receta.model_dump(mode="json")},
    )
