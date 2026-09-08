"""Interfaz del almacen de archivos.

Las rutas son claves relativas estilo POSIX ("org_1/ws_1/fuentes/x.parquet"),
nunca rutas del sistema: la implementacion decide donde viven. Ver
`app.almacen.rutas` para armarlas.
"""
import re
from abc import ABC, abstractmethod
from typing import BinaryIO

from app.nucleo.errores import ErrorApp

_SEGMENTO_VALIDO = re.compile(r"^[A-Za-z0-9._-]+$")


def validar_ruta(ruta: str) -> str:
    """Una ruta valida es relativa, con segmentos de letras, numeros, punto,
    guion y guion bajo. Nada de '..', barras dobles ni rutas absolutas: es lo
    que impide que un nombre de archivo subido escape del almacen."""
    if not ruta or ruta.startswith("/") or "\\" in ruta:
        raise ErrorApp("E-ALM-01", f"ruta: {ruta!r}")
    segmentos = ruta.split("/")
    for segmento in segmentos:
        if segmento in ("", ".", "..") or not _SEGMENTO_VALIDO.match(segmento):
            raise ErrorApp("E-ALM-01", f"ruta: {ruta!r}")
    return ruta


class AlmacenArchivos(ABC):
    @abstractmethod
    def guardar(self, ruta: str, datos: bytes | BinaryIO) -> None:
        """Escribe el archivo entero. Debe ser atomico: nunca queda un archivo
        a medio escribir bajo el nombre final."""

    @abstractmethod
    def abrir(self, ruta: str) -> BinaryIO:
        """Devuelve un archivo binario abierto para lectura. Cerrarlo."""

    def leer(self, ruta: str) -> bytes:
        with self.abrir(ruta) as archivo:
            return archivo.read()

    @abstractmethod
    def existe(self, ruta: str) -> bool: ...

    @abstractmethod
    def tamanio(self, ruta: str) -> int:
        """Bytes. E-ALM-02 si no existe."""

    @abstractmethod
    def eliminar(self, ruta: str) -> None:
        """Idempotente: borrar algo que no existe no es error."""

    @abstractmethod
    def listar(self, prefijo: str = "") -> list[str]:
        """Rutas que empiezan con `prefijo`, ordenadas."""

    @abstractmethod
    def uri_para_duckdb(self, ruta: str) -> str:
        """Lo que DuckDB puede leer con read_parquet(): un path local hoy,
        una URI s3:// cuando el almacen sea remoto."""
