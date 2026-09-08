"""Orquestacion de la ingesta.

`ingestar_archivo` es puro (bytes -> Parquet temporales + esquemas), sin
base de datos: es lo que prueban los tests de ingesta. `registrar_fuentes`
lleva esos resultados al almacen y al catalogo.
"""
import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path

import duckdb
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.almacen.base import AlmacenArchivos
from app.almacen.rutas import ruta_parquet_fuente
from app.catalogo.tablas import EstadoFuente, Fuente, Workspace
from app.ingesta.encabezado import normalizar_nombre_columna
from app.ingesta.lector_csv import TablaCruda, cargar_csv
from app.ingesta.lector_excel import cargar_excel
from app.ingesta.tipado import TAMANIO_MUESTRA, columna_sql, decidir_tipo, expresion_limpia, expresion_sql
from app.nucleo.errores import ErrorApp

EXTENSIONES_CSV = {".csv", ".txt", ".tsv"}
EXTENSIONES_EXCEL = {".xlsx", ".xlsm"}
EXTENSIONES_SOPORTADAS = EXTENSIONES_CSV | EXTENSIONES_EXCEL


@dataclass
class ColumnaEsquema:
    nombre: str
    nombre_origen: str | None
    tipo: str
    nulos: int
    invalidos: int
    detalle: dict = field(default_factory=dict)


@dataclass
class ResultadoTabla:
    nombre_tabla: str
    hoja: str | None
    formato: str
    esquema: list[ColumnaEsquema]
    filas: int
    ruta_parquet_temporal: Path
    opciones: dict

    def esquema_como_dicts(self) -> list[dict]:
        return [asdict(columna) for columna in self.esquema]


def validar_extension(nombre_archivo: str) -> str:
    extension = Path(nombre_archivo).suffix.lower()
    if extension not in EXTENSIONES_SOPORTADAS:
        raise ErrorApp("E-ING-05", f"archivo: {nombre_archivo!r}")
    return extension


def ingestar_archivo(datos: bytes, nombre_archivo: str, directorio_temporal: Path) -> list[ResultadoTabla]:
    """Bytes de un CSV o Excel -> una o mas tablas tipadas como Parquet en el
    directorio temporal. Excel: una por hoja con datos."""
    extension = validar_extension(nombre_archivo)
    base = normalizar_nombre_columna(Path(nombre_archivo).stem, 0)
    conexion = duckdb.connect()
    try:
        if extension in EXTENSIONES_CSV:
            tabla = cargar_csv(conexion, datos, "cruda", directorio_temporal)
            return [_tipar_y_escribir(conexion, tabla, base, None, "csv", directorio_temporal)]
        hojas = cargar_excel(conexion, datos, "cruda", directorio_temporal)
        if not hojas:
            raise ErrorApp("E-ING-03", f"archivo: {nombre_archivo!r}")
        resultados = []
        for nombre_hoja, tabla in hojas:
            nombre_tabla = base if len(hojas) == 1 else f"{base}_{normalizar_nombre_columna(nombre_hoja, 0)}"
            resultados.append(_tipar_y_escribir(conexion, tabla, nombre_tabla, nombre_hoja, "xlsx", directorio_temporal))
        return resultados
    finally:
        conexion.close()


def _tipar_y_escribir(
    conexion: duckdb.DuckDBPyConnection,
    tabla: TablaCruda,
    nombre_tabla: str,
    hoja: str | None,
    formato: str,
    directorio_temporal: Path,
) -> ResultadoTabla:
    relacion = tabla.nombre_relacion
    total = conexion.execute(f"SELECT count(*) FROM {relacion}").fetchone()[0]
    if total == 0:
        raise ErrorApp("E-ING-03", f"tabla: {nombre_tabla}")

    decisiones = {}
    for columna in tabla.columnas:
        limpio = expresion_limpia(columna)
        muestra = conexion.execute(
            f"SELECT DISTINCT {limpio} AS valor FROM {relacion} WHERE {limpio} IS NOT NULL LIMIT {TAMANIO_MUESTRA}"
        ).fetchall()
        decisiones[columna] = decidir_tipo([fila[0] for fila in muestra])

    expresiones = {columna: expresion_sql(columna, decision) for columna, decision in decisiones.items()}

    # Nulos e invalidos de cada columna en una sola pasada
    conteos_sql = ", ".join(
        f"count({expresion_limpia(columna)}), count({expresiones[columna]})" for columna in tabla.columnas
    )
    conteos = conexion.execute(f"SELECT {conteos_sql} FROM {relacion}").fetchone()

    esquema = []
    for posicion, columna in enumerate(tabla.columnas):
        no_nulos, validos = conteos[2 * posicion], conteos[2 * posicion + 1]
        esquema.append(
            ColumnaEsquema(
                nombre=columna,
                nombre_origen=tabla.columnas_origen[posicion] if posicion < len(tabla.columnas_origen) else None,
                tipo=decisiones[columna].tipo,
                nulos=total - no_nulos,
                invalidos=no_nulos - validos,
                detalle=decisiones[columna].detalle,
            )
        )

    seleccion = ", ".join(f"{expresiones[columna]} AS {columna_sql(columna)}" for columna in tabla.columnas)
    ruta_parquet = directorio_temporal / f"{relacion}.parquet"
    conexion.execute(f"COPY (SELECT {seleccion} FROM {relacion}) TO '{ruta_parquet.as_posix()}' (FORMAT PARQUET)")

    return ResultadoTabla(
        nombre_tabla=nombre_tabla,
        hoja=hoja,
        formato=formato,
        esquema=esquema,
        filas=total,
        ruta_parquet_temporal=ruta_parquet,
        opciones=tabla.opciones,
    )


def calcular_huella(nombre_tabla: str, esquema: list[dict]) -> str:
    """Identidad de una fuente: nombre + columnas con sus tipos. Cambia si
    aparece, desaparece o cambia de tipo una columna (base de la deteccion de
    cambios de esquema de la fase 4)."""
    firma = nombre_tabla + "|" + "|".join(f"{columna['nombre']}:{columna['tipo']}" for columna in esquema)
    return hashlib.sha256(firma.encode()).hexdigest()[:16]


def registrar_fuentes(
    sesion: Session,
    almacen: AlmacenArchivos,
    workspace: Workspace,
    resultados: list[ResultadoTabla],
    *,
    archivo_origen: str,
    ruta_original: str | None,
    usuario_id: int | None,
) -> list[tuple[Fuente, bool]]:
    """Guarda cada Parquet en el almacen y crea o REEMPLAZA la fila `fuente`
    (misma nombre_tabla en el workspace = resubida). Devuelve
    [(fuente, reemplazada)]."""
    registradas = []
    for resultado in resultados:
        esquema = resultado.esquema_como_dicts()
        fuente = sesion.scalar(
            select(Fuente).where(Fuente.workspace_id == workspace.id, Fuente.nombre_tabla == resultado.nombre_tabla)
        )
        reemplazada = fuente is not None
        if fuente is None:
            fuente = Fuente(workspace_id=workspace.id, nombre_tabla=resultado.nombre_tabla, creada_por_id=usuario_id)
            sesion.add(fuente)
            sesion.flush()  # necesita el id para la ruta del Parquet
        fuente.nombre = resultado.hoja or resultado.nombre_tabla
        fuente.archivo_origen = archivo_origen
        fuente.hoja = resultado.hoja
        fuente.formato = resultado.formato
        fuente.esquema = esquema
        fuente.filas = resultado.filas
        fuente.huella = calcular_huella(resultado.nombre_tabla, esquema)
        fuente.opciones = resultado.opciones
        fuente.ruta_original = ruta_original
        fuente.estado = EstadoFuente.LISTA
        fuente.error = None
        fuente.ruta_parquet = ruta_parquet_fuente(workspace.organizacion_id, workspace.id, fuente.id)
        with open(resultado.ruta_parquet_temporal, "rb") as archivo:
            almacen.guardar(fuente.ruta_parquet, archivo)
        registradas.append((fuente, reemplazada))
    sesion.commit()
    for fuente, _ in registradas:
        sesion.refresh(fuente)
    return registradas


def eliminar_fuente(sesion: Session, almacen: AlmacenArchivos, fuente: Fuente) -> None:
    if fuente.ruta_parquet:
        almacen.eliminar(fuente.ruta_parquet)
    if fuente.ruta_original:
        almacen.eliminar(fuente.ruta_original)
    sesion.delete(fuente)
    sesion.commit()
