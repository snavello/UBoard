"""Texto estructurado (fase 4): validar_receta (reglas que Pydantic no puede
expresar solas) y cargar_texto_estructurado (aplicar una receta ya
confirmada, deterministico). Puro, sin Postgres."""
import duckdb
import pytest

from app.ingesta.estructura import ColumnaReceta, RecetaTexto, cargar_texto_estructurado, validar_receta
from app.nucleo.errores import ErrorApp

def _linea_ancho_fijo(id_: int, nombre: str, importe: int) -> str:
    # id[0:3] + nombre[3:23] + importe[23:31], construido con formato para
    # no depender de contar espacios a mano en un literal.
    return f"{id_:03d}{nombre:<20}{importe:08d}"


LINEAS_ANCHO_FIJO = [
    _linea_ancho_fijo(1, "Ana Martinez", 150000),
    _linea_ancho_fijo(2, "Bruno Diaz", 87500),
    _linea_ancho_fijo(3, "Carla Ruiz", 230000),
]

RECETA_ANCHO_FIJO = RecetaTexto(
    modo="ancho_fijo",
    columnas=[
        ColumnaReceta(nombre="id", inicio=0, fin=3),
        ColumnaReceta(nombre="nombre", inicio=3, fin=23),
        ColumnaReceta(nombre="importe", inicio=23, fin=31),
    ],
)

LINEAS_REGEX = [
    "2026-01-05 Ana Martinez $150000",
    "2026-01-06 Bruno Diaz $87500",
]

RECETA_REGEX = RecetaTexto(
    modo="regex",
    patron=r"^(\d{4}-\d{2}-\d{2}) (.+?) \$(\d+)$",
    columnas=[ColumnaReceta(nombre="fecha"), ColumnaReceta(nombre="nombre"), ColumnaReceta(nombre="importe")],
)


def test_validar_receta_ancho_fijo_ok():
    assert validar_receta(LINEAS_ANCHO_FIJO, RECETA_ANCHO_FIJO) == []


def test_validar_receta_ancho_fijo_detecta_solape():
    receta = RECETA_ANCHO_FIJO.model_copy(deep=True)
    receta.columnas[1].inicio = 2  # se come 1 caracter de "id"
    errores = validar_receta(LINEAS_ANCHO_FIJO, receta)
    assert any("solapa" in error for error in errores)


def test_validar_receta_ancho_fijo_detecta_que_no_cubre_la_linea():
    receta = RecetaTexto(modo="ancho_fijo", columnas=[ColumnaReceta(nombre="id", inicio=0, fin=3)])
    errores = validar_receta(LINEAS_ANCHO_FIJO, receta)
    assert any("cubren hasta" in error for error in errores)


def test_validar_receta_nombres_repetidos_tras_normalizar():
    receta = RecetaTexto(
        modo="ancho_fijo",
        columnas=[ColumnaReceta(nombre="Id Venta", inicio=0, fin=3), ColumnaReceta(nombre="id_venta", inicio=3, fin=31)],
    )
    errores = validar_receta(LINEAS_ANCHO_FIJO, receta)
    assert any("repetidos" in error for error in errores)


def test_validar_receta_regex_ok():
    assert validar_receta(LINEAS_REGEX, RECETA_REGEX) == []


def test_validar_receta_regex_no_compila():
    receta = RecetaTexto(modo="regex", patron="(no cierra", columnas=[ColumnaReceta(nombre="x")])
    errores = validar_receta(LINEAS_REGEX, receta)
    assert any("no compila" in error for error in errores)


def test_validar_receta_regex_grupos_no_coinciden_con_columnas():
    receta = RecetaTexto(modo="regex", patron=r"^(\d+)-(\d+)$", columnas=[ColumnaReceta(nombre="unica")])
    errores = validar_receta(["1-2"], receta)
    assert any("2 grupo" in error for error in errores)


def test_validar_receta_regex_matchea_poco_de_la_muestra():
    receta = RecetaTexto(modo="regex", patron=r"^ZZZ(\d+)$", columnas=[ColumnaReceta(nombre="x")])
    errores = validar_receta(LINEAS_REGEX, receta)
    assert any("solo matchea" in error for error in errores)


def test_cargar_texto_estructurado_ancho_fijo(tmp_path):
    conexion = duckdb.connect()
    try:
        tabla = cargar_texto_estructurado(conexion, "\n".join(LINEAS_ANCHO_FIJO).encode(), "cruda", RECETA_ANCHO_FIJO, tmp_path)
        assert tabla.columnas == ["id", "nombre", "importe"]
        filas = conexion.execute('SELECT id, nombre, importe FROM cruda ORDER BY id').fetchall()
        assert filas == [
            ("001", "Ana Martinez", "00150000"),
            ("002", "Bruno Diaz", "00087500"),
            ("003", "Carla Ruiz", "00230000"),
        ]
    finally:
        conexion.close()


def test_cargar_texto_estructurado_regex(tmp_path):
    conexion = duckdb.connect()
    try:
        tabla = cargar_texto_estructurado(conexion, "\n".join(LINEAS_REGEX).encode(), "cruda", RECETA_REGEX, tmp_path)
        assert tabla.columnas == ["fecha", "nombre", "importe"]
        filas = conexion.execute("SELECT fecha, nombre, importe FROM cruda ORDER BY fecha").fetchall()
        assert filas == [("2026-01-05", "Ana Martinez", "150000"), ("2026-01-06", "Bruno Diaz", "87500")]
    finally:
        conexion.close()


def test_cargar_texto_estructurado_fila_que_no_matchea_regex_queda_nula_no_se_descarta(tmp_path):
    lineas = LINEAS_REGEX + ["esto no matchea para nada"]
    conexion = duckdb.connect()
    try:
        tabla = cargar_texto_estructurado(conexion, "\n".join(lineas).encode(), "cruda", RECETA_REGEX, tmp_path)
        total = conexion.execute("SELECT count(*) FROM cruda").fetchone()[0]
        assert total == 3  # nunca se descarta una fila
        nulas = conexion.execute("SELECT count(*) FROM cruda WHERE fecha IS NULL AND nombre IS NULL AND importe IS NULL").fetchone()[0]
        assert nulas == 1
    finally:
        conexion.close()


def test_cargar_texto_estructurado_archivo_vacio_e_ing_03(tmp_path):
    conexion = duckdb.connect()
    try:
        with pytest.raises(ErrorApp) as error:
            cargar_texto_estructurado(conexion, b"   \n\n  ", "cruda", RECETA_ANCHO_FIJO, tmp_path)
        assert error.value.codigo == "E-ING-03"
    finally:
        conexion.close()
