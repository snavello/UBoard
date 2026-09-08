"""Los 5 CSV sinteticos se generan y se ingestan completos; la suciedad de
cada uno queda resuelta como se documenta en datos_prueba/README.md."""
import duckdb
import pytest

from app.ingesta.procesador import ResultadoTabla, ingestar_archivo
from scripts.generar_datos_prueba import CANTIDAD_VENTAS, MEDIOS_PAGO, PRODUCTOS, VENDEDORES, generar


@pytest.fixture(scope="module")
def resultados(tmp_path_factory) -> dict[str, ResultadoTabla]:
    raiz = tmp_path_factory.mktemp("datos_prueba")
    rutas = generar(raiz / "csv")
    salida = {}
    for nombre, ruta in rutas.items():
        directorio = raiz / f"ingesta_{nombre}"
        directorio.mkdir()
        salida[nombre] = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
    return salida


def _columna(resultado: ResultadoTabla, nombre: str):
    return next(columna for columna in resultado.esquema if columna.nombre == nombre)


def _uri(resultado: ResultadoTabla) -> str:
    return resultado.ruta_parquet_temporal.as_posix()


def test_ventas_fechas_mezcladas_huerfanos_y_moneda(resultados):
    ventas = resultados["ventas"]
    assert ventas.filas == CANTIDAD_VENTAS
    assert [columna.nombre for columna in ventas.esquema] == [
        "id_venta", "fecha", "vendedor", "id_producto", "cantidad", "precio_unitario", "importe",
    ]
    assert [columna.nombre_origen for columna in ventas.esquema][:2] == ["IdVenta", "Fecha"]
    fecha = _columna(ventas, "fecha")
    assert fecha.tipo == "fecha"
    assert set(fecha.detalle["formatos"]) == {"%Y-%m-%d", "%d/%m/%Y"}
    assert fecha.invalidos == 0
    vendedor = _columna(ventas, "vendedor")
    assert vendedor.tipo == "entero"
    assert 50 < vendedor.nulos < 150  # ~3% vacios
    importe = _columna(ventas, "importe")
    assert importe.tipo == "decimal"
    assert importe.invalidos == 0  # los "$ 1250.50" convirtieron
    assert importe.nulos == 0


def test_productos_latin1_coma_decimal_y_booleano(resultados):
    productos = resultados["productos"]
    assert productos.filas == len(PRODUCTOS)
    assert productos.opciones["codificacion"] == "cp1252"
    assert productos.opciones["delimitador"] == ";"
    assert _columna(productos, "precio_lista").tipo == "decimal"
    assert _columna(productos, "precio_lista").detalle["estilo_decimal"] == "coma"
    assert _columna(productos, "activo").tipo == "booleano"
    nombres = [fila[0] for fila in duckdb.sql(f"SELECT nombre FROM read_parquet('{_uri(productos)}')").fetchall()]
    assert "Dulce de Leche Ñandú 400g" in nombres
    assert "Aceite Girasol Cañuelas 1,5L" in nombres
    precio = duckdb.sql(f"SELECT precio_lista FROM read_parquet('{_uri(productos)}') WHERE id_producto = 2").fetchone()[0]
    assert precio == 1320.5


def test_pagos_titulos_saltados_y_coma_decimal(resultados):
    pagos = resultados["pagos"]
    assert pagos.opciones["filas_saltadas"] == 2
    assert pagos.opciones["delimitador"] == ";"
    assert pagos.filas >= CANTIDAD_VENTAS
    assert _columna(pagos, "monto").tipo == "decimal"
    assert _columna(pagos, "fecha_pago").tipo == "fecha"
    assert _columna(pagos, "fecha_pago").detalle["formatos"] == ["%d/%m/%Y"]
    assert _columna(pagos, "cuotas").tipo == "entero"


def test_medios_pago_sin_bom_en_el_primer_encabezado(resultados):
    medios = resultados["medios_pago"]
    assert medios.opciones["codificacion"] == "utf-8-sig"
    assert medios.esquema[0].nombre == "id_medio_pago"
    assert medios.esquema[0].nombre_origen == "id_medio_pago"
    assert medios.filas == len(MEDIOS_PAGO)


def test_vendedores_nombres_recortados(resultados):
    vendedores = resultados["vendedores"]
    assert vendedores.filas == len(VENDEDORES)
    con_espacios = duckdb.sql(
        f"SELECT count(*) FROM read_parquet('{_uri(vendedores)}') WHERE nombre <> trim(nombre)"
    ).fetchone()[0]
    assert con_espacios == 0
    assert _columna(vendedores, "email").nulos == 3
    assert _columna(vendedores, "fecha_ingreso").tipo == "fecha"


def test_hay_huerfanos_para_que_la_inferencia_tenga_evidencia(resultados):
    huerfanos = duckdb.sql(
        f"""
        SELECT count(*) FROM read_parquet('{_uri(resultados["ventas"])}') v
        WHERE v.vendedor IS NOT NULL
          AND v.vendedor NOT IN (SELECT id_vendedor FROM read_parquet('{_uri(resultados["vendedores"])}'))
        """
    ).fetchone()[0]
    assert huerfanos > 0
    pagos_huerfanos = duckdb.sql(
        f"""
        SELECT count(*) FROM read_parquet('{_uri(resultados["pagos"])}') p
        WHERE p.id_venta NOT IN (SELECT id_venta FROM read_parquet('{_uri(resultados["ventas"])}'))
        """
    ).fetchone()[0]
    assert pagos_huerfanos > 0
