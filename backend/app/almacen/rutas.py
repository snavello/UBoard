"""Convencion de rutas dentro del almacen. Todo lo de un workspace vive bajo
su prefijo, asi borrar o migrar un workspace es mover un directorio (o un
prefijo de bucket)."""
import re
import unicodedata

_NO_PERMITIDO = re.compile(r"[^A-Za-z0-9._-]+")


def prefijo_workspace(organizacion_id: int, workspace_id: int) -> str:
    return f"org_{organizacion_id}/ws_{workspace_id}"


def ruta_parquet_fuente(organizacion_id: int, workspace_id: int, fuente_id: int) -> str:
    return f"{prefijo_workspace(organizacion_id, workspace_id)}/fuentes/{fuente_id}.parquet"


def ruta_subida_original(organizacion_id: int, workspace_id: int, fuente_id: int, nombre_archivo: str) -> str:
    """El archivo tal cual se subio, para poder reprocesarlo."""
    return f"{prefijo_workspace(organizacion_id, workspace_id)}/subidas/{fuente_id}/{nombre_seguro(nombre_archivo)}"


def nombre_seguro(nombre_archivo: str) -> str:
    """Convierte un nombre de archivo cualquiera en un segmento valido de ruta:
    sin tildes, sin espacios, sin directorios. 'Ventas 2026 (marzo).csv' ->
    'Ventas_2026_marzo.csv'."""
    solo_nombre = nombre_archivo.replace("\\", "/").split("/")[-1]
    sin_tildes = unicodedata.normalize("NFKD", solo_nombre).encode("ascii", "ignore").decode()
    limpio = _NO_PERMITIDO.sub("_", sin_tildes)
    limpio = re.sub(r"_+", "_", limpio)
    # "marzo_.csv" -> "marzo.csv": el guion bajo pegado a un punto no aporta
    limpio = re.sub(r"_\.", ".", limpio)
    limpio = re.sub(r"\._", ".", limpio)
    limpio = limpio.strip("._")
    return limpio or "archivo"
