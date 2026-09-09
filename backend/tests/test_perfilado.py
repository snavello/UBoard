"""Perfilado puro (DuckDB en memoria, sin Postgres) sobre los 5 CSV sinteticos
y sobre tablas armadas a mano para los casos borde."""
import duckdb
import pytest

from app.ingesta.procesador import ResultadoTabla, ingestar_archivo
from app.perfilado import PerfilFuente, perfilar
from scripts.generar_datos_prueba import CANTIDAD_VENTAS, PRODUCTOS, VENDEDORES, generar


@pytest.fixture(scope="module")
def perfiles(tmp_path_factory) -> dict[str, PerfilFuente]:
    raiz = tmp_path_factory.mktemp("perfilado")
    rutas = generar(raiz / "csv")
    salida = {}
    for nombre, ruta in rutas.items():
        directorio = raiz / f"ingesta_{nombre}"
        directorio.mkdir()
        resultado: ResultadoTabla = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
        salida[nombre] = PerfilFuente.model_validate(resultado.perfil)
    return salida


def test_el_perfil_viaja_en_el_resultado_de_la_ingesta_y_es_json(perfiles):
    ventas = perfiles["ventas"]
    assert ventas.nombre_tabla == "ventas"
    assert ventas.filas == CANTIDAD_VENTAS
    assert [columna.nombre for columna in ventas.columnas] == [
        "id_venta",
        "fecha",
        "vendedor",
        "id_producto",
        "cantidad",
        "precio_unitario",
        "importe",
    ]
    # Fechas como ISO, no como objetos date
    assert isinstance(ventas.columna("fecha").minimo, str)


def test_ventas_candidata_unica_y_huerfanos_visibles(perfiles):
    ventas = perfiles["ventas"]
    assert ventas.candidatas_clave == ["id_venta"]
    id_venta = ventas.columna("id_venta")
    assert id_venta.unica and id_venta.nulos == 0 and id_venta.distintos == CANTIDAD_VENTAS
    assert (id_venta.minimo, id_venta.maximo) == (1, CANTIDAD_VENTAS)

    vendedor = ventas.columna("vendedor")
    assert not vendedor.unica
    assert vendedor.nulos > 0, "3 % de ventas sin vendedor"
    assert vendedor.maximo == 99, "el vendedor huerfano queda a la vista en el maximo"
    assert vendedor.distintos == len(VENDEDORES) + 1

    fecha = ventas.columna("fecha")
    assert fecha.minimo == "2025-09-01" and fecha.maximo == "2026-08-31"
    assert fecha.distintos == 365

    importe = ventas.columna("importe")
    assert importe.tipo == "decimal" and importe.promedio > 0 and importe.minimo > 0


def test_productos_texto_con_patrones_largos_y_top_valores(perfiles):
    productos = perfiles["productos"]
    assert productos.filas == len(PRODUCTOS)
    # nombre tambien es unica: candidata, pero el id va primero (orden del esquema)
    assert productos.candidatas_clave == ["id_producto", "nombre"]
    categoria = productos.columna("categoria")
    assert categoria.tipo == "texto" and categoria.patron is None
    assert categoria.longitud_minima >= 5 and categoria.longitud_maxima >= categoria.longitud_minima
    assert sum(top.cantidad for top in categoria.top_valores) == len(PRODUCTOS)
    assert categoria.top_valores[0].cantidad >= categoria.top_valores[-1].cantidad
    activo = productos.columna("activo")
    assert activo.tipo == "booleano" and activo.distintos == 2
    assert {top.valor for top in activo.top_valores} == {True, False}


def test_vendedores_email_con_patron_y_nulos(perfiles):
    vendedores = perfiles["vendedores"]
    email = vendedores.columna("email")
    assert email.patron == "email"
    assert email.nulos > 0, "hay vendedores sin email"
    assert not email.unica
    sucursal = vendedores.columna("sucursal")
    assert sucursal.distintos == 3
    assert [top.valor for top in sucursal.top_valores] == ["Centro", "Norte", "Oeste"]


def test_pagos_y_medios_de_pago(perfiles):
    pagos = perfiles["pagos"]
    assert pagos.candidatas_clave == ["id_pago"]
    assert pagos.columna("id_venta").distintos < pagos.filas, "hay ventas pagadas en dos partes"
    medios = perfiles["medios_pago"]
    assert medios.candidatas_clave[0] == "id_medio_pago"


def _perfil_de(sql: str, columnas: list[tuple[str, str]]) -> PerfilFuente:
    conexion = duckdb.connect()
    conexion.execute(f"CREATE TABLE t AS {sql}")
    return perfilar(conexion, "t", "t", columnas)


def test_patrones_codigo_numerico_y_url():
    perfil = _perfil_de(
        "SELECT * FROM (VALUES ('AB-001', '00123', 'https://a.com/x'), ('AB-002', '00124', 'http://b.org'), ('ZZ-9', '7', 'https://c.net/y')) AS v(codigo, numero, sitio)",
        [("codigo", "texto"), ("numero", "texto"), ("sitio", "texto")],
    )
    assert perfil.columna("codigo").patron == "codigo"
    assert perfil.columna("numero").patron == "numerico"
    assert perfil.columna("sitio").patron == "url"
    assert perfil.candidatas_clave == ["codigo", "numero", "sitio"]


def test_columna_toda_nula_y_tabla_vacia():
    perfil = _perfil_de(
        "SELECT * FROM (VALUES (1, NULL), (2, NULL)) AS v(id, vacia)", [("id", "entero"), ("vacia", "texto")]
    )
    vacia = perfil.columna("vacia")
    assert vacia.nulos == 2 and vacia.distintos == 0 and not vacia.unica
    assert vacia.top_valores == [] and vacia.patron is None and vacia.minimo is None
    assert perfil.candidatas_clave == ["id"]

    conexion = duckdb.connect()
    conexion.execute("CREATE TABLE t (id INTEGER)")
    vacio = perfilar(conexion, "t", "t", [("id", "entero")])
    assert vacio.filas == 0 and not vacio.columnas[0].unica and vacio.candidatas_clave == []


def test_un_decimal_no_es_candidata_a_clave():
    perfil = _perfil_de("SELECT * FROM (VALUES (1.5), (2.5)) AS v(monto)", [("monto", "decimal")])
    assert perfil.columna("monto").unica
    assert perfil.candidatas_clave == []
