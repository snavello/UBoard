"""AlmacenLocal: archivos en un directorio del disco (desarrollo, y el volumen
`uboard-almacen` en Docker)."""
import os
import secrets
import shutil
from pathlib import Path
from typing import BinaryIO

from app.almacen.base import AlmacenArchivos, validar_ruta
from app.nucleo.errores import ErrorApp

SUFIJO_TEMPORAL = ".tmp-"


class AlmacenLocal(AlmacenArchivos):
    def __init__(self, raiz: Path | str):
        self.raiz = Path(raiz).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _ruta_fisica(self, ruta: str) -> Path:
        validar_ruta(ruta)
        destino = (self.raiz / ruta).resolve()
        # Doble seguro ademas de validar_ruta: el destino tiene que quedar adentro
        if not destino.is_relative_to(self.raiz):
            raise ErrorApp("E-ALM-01", f"ruta: {ruta!r}")
        return destino

    def guardar(self, ruta: str, datos: bytes | BinaryIO) -> None:
        destino = self._ruta_fisica(ruta)
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Se escribe en un temporal al lado y se renombra: os.replace es atomico
        # en el mismo sistema de archivos, asi nadie lee un Parquet a medias.
        temporal = destino.with_name(f"{destino.name}{SUFIJO_TEMPORAL}{secrets.token_hex(4)}")
        try:
            with open(temporal, "wb") as archivo:
                if isinstance(datos, (bytes, bytearray)):
                    archivo.write(datos)
                else:
                    shutil.copyfileobj(datos, archivo)
            os.replace(temporal, destino)
        finally:
            if temporal.exists():
                temporal.unlink()

    def abrir(self, ruta: str) -> BinaryIO:
        destino = self._ruta_fisica(ruta)
        if not destino.is_file():
            raise ErrorApp("E-ALM-02", f"ruta: {ruta!r}")
        return open(destino, "rb")

    def existe(self, ruta: str) -> bool:
        return self._ruta_fisica(ruta).is_file()

    def tamanio(self, ruta: str) -> int:
        destino = self._ruta_fisica(ruta)
        if not destino.is_file():
            raise ErrorApp("E-ALM-02", f"ruta: {ruta!r}")
        return destino.stat().st_size

    def eliminar(self, ruta: str) -> None:
        self._ruta_fisica(ruta).unlink(missing_ok=True)

    def listar(self, prefijo: str = "") -> list[str]:
        rutas = []
        for archivo in self.raiz.rglob("*"):
            if not archivo.is_file() or SUFIJO_TEMPORAL in archivo.name:
                continue
            ruta = archivo.relative_to(self.raiz).as_posix()
            if ruta.startswith(prefijo):
                rutas.append(ruta)
        return sorted(rutas)

    def uri_para_duckdb(self, ruta: str) -> str:
        return self._ruta_fisica(ruta).as_posix()
