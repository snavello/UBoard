"""AlmacenLocal: guardar, leer, listar, borrar, rutas seguras y compatibilidad
con DuckDB. Puro, sin Postgres."""
import os
from io import BytesIO
from pathlib import Path

import duckdb
import pytest

from app.almacen import AlmacenLocal, obtener_almacen
from app.almacen.rutas import nombre_seguro, prefijo_workspace, ruta_parquet_fuente, ruta_subida_original
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp

RUTA = "org_1/ws_1/fuentes/1.parquet"


@pytest.fixture
def almacen(tmp_path) -> AlmacenLocal:
    return AlmacenLocal(tmp_path / "almacen")


def test_guardar_leer_existe_tamanio_y_eliminar(almacen):
    assert not almacen.existe(RUTA)
    almacen.guardar(RUTA, b"hola")
    assert almacen.existe(RUTA)
    assert almacen.leer(RUTA) == b"hola"
    assert almacen.tamanio(RUTA) == 4
    with almacen.abrir(RUTA) as archivo:
        assert archivo.read() == b"hola"
    almacen.eliminar(RUTA)
    assert not almacen.existe(RUTA)
    almacen.eliminar(RUTA)  # idempotente


def test_guardar_desde_un_stream(almacen):
    almacen.guardar(RUTA, BytesIO(b"desde stream"))
    assert almacen.leer(RUTA) == b"desde stream"


def test_sobrescribir_reemplaza_y_no_deja_temporales(almacen):
    almacen.guardar(RUTA, b"version 1")
    almacen.guardar(RUTA, b"version 2, mas larga")
    assert almacen.leer(RUTA) == b"version 2, mas larga"
    assert almacen.listar() == [RUTA]
    directorio = almacen.raiz / "org_1" / "ws_1" / "fuentes"
    assert os.listdir(directorio) == ["1.parquet"]


def test_listar_por_prefijo(almacen):
    for ruta in ["org_1/ws_1/fuentes/2.parquet", "org_1/ws_1/fuentes/1.parquet", "org_1/ws_2/fuentes/1.parquet", "org_2/ws_3/x.csv"]:
        almacen.guardar(ruta, b"x")
    assert almacen.listar("org_1/ws_1/") == ["org_1/ws_1/fuentes/1.parquet", "org_1/ws_1/fuentes/2.parquet"]
    assert almacen.listar("org_2") == ["org_2/ws_3/x.csv"]
    assert len(almacen.listar()) == 4
    assert almacen.listar("nada") == []


@pytest.mark.parametrize(
    "ruta",
    ["", "/absoluta/x", "../afuera", "a/../b", "a//b", "a\\b", "a/./b", "con espacio.csv", "nandu-ñ.csv", "a/"],
)
def test_rutas_invalidas_se_rechazan(almacen, ruta):
    with pytest.raises(ErrorApp) as error:
        almacen.guardar(ruta, b"x")
    assert error.value.codigo == "E-ALM-01"
    assert almacen.listar() == []


def test_abrir_o_medir_inexistente(almacen):
    with pytest.raises(ErrorApp) as error:
        almacen.abrir("org_1/no.parquet")
    assert error.value.codigo == "E-ALM-02"
    with pytest.raises(ErrorApp):
        almacen.tamanio("org_1/no.parquet")


def test_uri_para_duckdb_es_una_ruta_local_absoluta(almacen):
    uri = almacen.uri_para_duckdb(RUTA)
    assert Path(uri).is_absolute()
    assert uri.endswith("/org_1/ws_1/fuentes/1.parquet")
    assert "\\" not in uri


def test_duckdb_lee_un_parquet_guardado_en_el_almacen(almacen, tmp_path):
    origen = tmp_path / "origen.parquet"
    duckdb.sql("SELECT range AS id, range * 10 AS monto FROM range(7)").write_parquet(str(origen))
    with open(origen, "rb") as archivo:
        almacen.guardar(RUTA, archivo)
    uri = almacen.uri_para_duckdb(RUTA)
    filas, suma = duckdb.sql(f"SELECT count(*), sum(monto) FROM read_parquet('{uri}')").fetchone()
    assert (filas, suma) == (7, 210)


def test_obtener_almacen_usa_la_configuracion():
    almacen = obtener_almacen()
    assert isinstance(almacen, AlmacenLocal)
    assert almacen.raiz == obtener_configuracion().ruta_almacen.resolve()


def test_convencion_de_rutas():
    assert prefijo_workspace(1, 2) == "org_1/ws_2"
    assert ruta_parquet_fuente(1, 2, 3) == "org_1/ws_2/fuentes/3.parquet"
    assert ruta_subida_original(1, 2, 3, "Ventas marzo.csv") == "org_1/ws_2/subidas/3/Ventas_marzo.csv"


@pytest.mark.parametrize(
    "nombre, esperado",
    [
        ("Ventas 2026 (marzo).csv", "Ventas_2026_marzo.csv"),
        ("Ñandú año.xlsx", "Nandu_ano.xlsx"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\x\\datos.csv", "datos.csv"),
        ("???", "archivo"),
        ("  .oculto  ", "oculto"),
    ],
)
def test_nombre_seguro(nombre, esperado):
    assert nombre_seguro(nombre) == esperado
