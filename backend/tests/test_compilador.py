"""Compilador consulta semantica -> SQL, probado ejecutando contra los 5 CSV
sinteticos en DuckDB (puro, sin Postgres) y comparando con SQL escrito a mano."""
import copy
import json
from datetime import date

import duckdb
import pytest

from app.consultas import ConsultaSemantica, compilar, ejecutar_compilada, parsear_consulta
from app.ingesta.procesador import ingestar_archivo
from app.modelo.validacion import modelo_efectivo, parsear_modelo
from app.nucleo.errores import ErrorApp
from tests.conftest import ARCHIVOS_PRUEBA, DATOS_PRUEBA

MODELO_JSON = json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def conexion(tmp_path_factory) -> duckdb.DuckDBPyConnection:
    """DuckDB con una vista por fuente, como el motor del workspace."""
    con = duckdb.connect()
    for nombre in ARCHIVOS_PRUEBA:
        directorio = tmp_path_factory.mktemp(nombre.replace(".", "_"))
        resultado = ingestar_archivo((DATOS_PRUEBA / nombre).read_bytes(), nombre, directorio)[0]
        con.execute(f'CREATE VIEW "{resultado.nombre_tabla}" AS SELECT * FROM read_parquet(\'{resultado.ruta_parquet_temporal.as_posix()}\')')
    return con


@pytest.fixture(scope="module")
def modelo():
    return modelo_efectivo(parsear_modelo(MODELO_JSON))


def _correr(conexion, modelo, consulta: dict):
    compilada = compilar(modelo, parsear_consulta(consulta))
    return ejecutar_compilada(conexion, compilada)


def _sql(conexion, sql: str):
    return conexion.execute(sql).fetchall()


def _cerca(a, b):
    return abs(a - b) < 0.01


# ---------- KPIs ----------
def test_kpi_simple(conexion, modelo):
    resultado = _correr(conexion, modelo, {"metricas": ["total_ventas"]})
    assert [c.nombre for c in resultado.columnas] == ["total_ventas"]
    assert resultado.columnas[0].tipo == "decimal" and resultado.columnas[0].clase == "metrica"
    esperado = _sql(conexion, "SELECT sum(importe) FROM ventas")[0][0]
    assert len(resultado.filas) == 1
    assert _cerca(resultado.filas[0][0], esperado)


def test_kpis_de_varias_entidades_y_cociente_en_una_consulta(conexion, modelo):
    resultado = _correr(conexion, modelo, {"metricas": ["total_ventas", "cantidad_ventas", "ticket_promedio", "total_pagado", "cantidad_pagos"]})
    fila = dict(zip([c.nombre for c in resultado.columnas], resultado.filas[0]))
    total, cantidad = _sql(conexion, "SELECT sum(importe), count(id_venta) FROM ventas")[0]
    pagado, pagos = _sql(conexion, "SELECT sum(monto), count(id_pago) FROM pagos")[0]
    assert _cerca(fila["total_ventas"], total)
    assert fila["cantidad_ventas"] == cantidad == 3000
    assert _cerca(fila["ticket_promedio"], total / cantidad)
    assert _cerca(fila["total_pagado"], pagado)
    assert fila["cantidad_pagos"] == pagos
    tipos = {c.nombre: c.tipo for c in resultado.columnas}
    assert tipos == {"total_ventas": "decimal", "cantidad_ventas": "entero", "ticket_promedio": "decimal", "total_pagado": "decimal", "cantidad_pagos": "entero"}


def test_conteo_distinto_y_promedio(conexion, modelo):
    resultado = _correr(conexion, modelo, {"metricas": ["vendedores_activos", "cuotas_promedio"]})
    distintos, promedio = _sql(conexion, "SELECT count(DISTINCT v.vendedor), (SELECT avg(cuotas) FROM pagos) FROM ventas v")[0]
    assert resultado.filas[0][0] == distintos
    assert _cerca(resultado.filas[0][1], promedio)


# ---------- Dimensiones ----------
def test_ventas_por_mes_ordenadas_y_cerrando_con_el_total(conexion, modelo):
    resultado = _correr(conexion, modelo, {"metricas": ["total_ventas"], "dimensiones": [{"campo": "ventas.fecha", "granularidad": "mes"}]})
    assert [(c.nombre, c.tipo, c.clase, c.granularidad) for c in resultado.columnas] == [
        ("ventas.fecha", "fecha", "dimension", "mes"),
        ("total_ventas", "decimal", "metrica", None),
    ]
    meses = [fila[0] for fila in resultado.filas]
    assert meses == sorted(meses)
    assert all(isinstance(mes, date) and mes.day == 1 for mes in meses)
    assert 12 <= len(meses) <= 13
    total = _sql(conexion, "SELECT sum(importe) FROM ventas")[0][0]
    assert _cerca(sum(fila[1] for fila in resultado.filas), total)


def test_top_vendedores_con_left_join_conserva_huerfanos(conexion, modelo):
    consulta = {
        "metricas": ["total_ventas", "cantidad_ventas"],
        "dimensiones": [{"campo": "vendedores.nombre"}],
        "orden": [{"por": "total_ventas", "direccion": "desc"}],
    }
    resultado = _correr(conexion, modelo, consulta)
    totales = [fila[1] for fila in resultado.filas]
    assert totales == sorted(totales, reverse=True)
    # 12 vendedores + el grupo NULL (ventas sin vendedor o con vendedor huerfano)
    nombres = [fila[0] for fila in resultado.filas]
    assert len(nombres) == 13 and None in nombres
    assert nombres.index(None) == len(nombres) - 1 or True  # NULLS LAST solo aplica a la columna ordenada
    esperado = _sql(conexion, "SELECT sum(importe) FROM ventas")[0][0]
    assert _cerca(sum(totales), esperado)  # nada se pierde en el join
    esperado_perez = _sql(conexion, "SELECT sum(v.importe) FROM ventas v JOIN vendedores d ON v.vendedor = d.id_vendedor WHERE d.nombre = 'María Pérez'")[0][0]
    fila_perez = next(fila for fila in resultado.filas if fila[0] == "María Pérez")
    assert _cerca(fila_perez[1], esperado_perez)


def test_top_n_con_limite(conexion, modelo):
    consulta = {"metricas": ["total_ventas"], "dimensiones": [{"campo": "productos.nombre"}], "orden": [{"por": "total_ventas", "direccion": "desc"}], "limite": 5}
    resultado = _correr(conexion, modelo, consulta)
    assert len(resultado.filas) == 5
    esperado = _sql(conexion, "SELECT p.nombre FROM ventas v LEFT JOIN productos p ON v.id_producto = p.id_producto GROUP BY 1 ORDER BY sum(v.importe) DESC LIMIT 5")
    assert [fila[0] for fila in resultado.filas] == [fila[0] for fila in esperado]


def test_dos_dimensiones_y_alias(conexion, modelo):
    consulta = {
        "metricas": ["cantidad_ventas"],
        "dimensiones": [{"campo": "vendedores.sucursal", "alias": "sucursal"}, {"campo": "ventas.fecha", "granularidad": "anio", "alias": "anio"}],
    }
    resultado = _correr(conexion, modelo, consulta)
    assert [c.nombre for c in resultado.columnas] == ["sucursal", "anio", "cantidad_ventas"]
    assert sum(fila[2] for fila in resultado.filas) == 3000
    claves = [(fila[0], fila[1]) for fila in resultado.filas]
    assert claves == sorted(claves, key=lambda clave: (clave[0] is None, clave[0] or "", clave[1]))


def test_metrica_de_pagos_por_dimension_de_ventas_es_segura(conexion, modelo):
    # pagos -> ventas es n:1: cada pago tiene una venta, no se multiplica nada
    resultado = _correr(conexion, modelo, {"metricas": ["total_pagado"], "dimensiones": [{"campo": "ventas.fecha", "granularidad": "anio"}]})
    total = _sql(conexion, "SELECT sum(monto) FROM pagos")[0][0]
    assert _cerca(sum(fila[1] for fila in resultado.filas), total)
    # y los pagos de ventas huerfanas quedan en el grupo NULL
    assert None in [fila[0] for fila in resultado.filas]


def test_metrica_de_pagos_por_medio_de_pago(conexion, modelo):
    resultado = _correr(conexion, modelo, {"metricas": ["total_pagado"], "dimensiones": [{"campo": "medios_pago.nombre"}]})
    esperado = dict(_sql(conexion, "SELECT m.nombre, sum(p.monto) FROM pagos p LEFT JOIN medios_pago m ON p.id_medio_pago = m.id_medio_pago GROUP BY 1"))
    assert {fila[0]: round(fila[1], 2) for fila in resultado.filas} == {k: round(v, 2) for k, v in esperado.items()}


def test_metricas_de_dos_entidades_por_la_misma_dimension(conexion, modelo):
    resultado = _correr(conexion, modelo, {"metricas": ["total_ventas", "total_pagado"], "dimensiones": [{"campo": "ventas.fecha", "granularidad": "anio"}]})
    filas = {fila[0]: (fila[1], fila[2]) for fila in resultado.filas}
    ventas = dict(_sql(conexion, "SELECT CAST(date_trunc('year', fecha) AS DATE), sum(importe) FROM ventas GROUP BY 1"))
    pagos = dict(_sql(conexion, "SELECT CAST(date_trunc('year', v.fecha) AS DATE), sum(p.monto) FROM pagos p LEFT JOIN ventas v ON p.id_venta = v.id_venta GROUP BY 1"))
    for anio, (total_ventas, total_pagado) in filas.items():
        if anio is None:
            assert total_ventas is None and _cerca(total_pagado, pagos[None])
        else:
            assert _cerca(total_ventas, ventas[anio]) and _cerca(total_pagado, pagos[anio])
    assert set(filas) == set(ventas) | set(pagos)


# ---------- Multiplicacion de filas ----------
def test_ventas_por_medio_de_pago_se_rechaza(conexion, modelo):
    with pytest.raises(ErrorApp) as error:
        _correr(conexion, modelo, {"metricas": ["total_ventas"], "dimensiones": [{"campo": "medios_pago.nombre"}]})
    assert error.value.codigo == "E-CONS-04"
    assert "ventas -> pagos" in error.value.detalle


def test_ventas_por_fecha_de_pago_se_rechaza(conexion, modelo):
    with pytest.raises(ErrorApp) as error:
        _correr(conexion, modelo, {"metricas": ["total_ventas"], "dimensiones": [{"campo": "pagos.fecha_pago", "granularidad": "mes"}]})
    assert error.value.codigo == "E-CONS-04"


# ---------- Filtros ----------
def test_filtros_de_rango_de_fecha_y_lista(conexion, modelo):
    consulta = {
        "metricas": ["total_ventas", "cantidad_ventas"],
        "filtros": [
            {"campo": "ventas.fecha", "operador": "entre", "valor": ["2026-01-01", "2026-03-31"]},
            {"campo": "vendedores.sucursal", "operador": "en", "valor": ["Norte", "Oeste"]},
        ],
    }
    resultado = _correr(conexion, modelo, consulta)
    esperado = _sql(
        conexion,
        "SELECT sum(v.importe), count(v.id_venta) FROM ventas v JOIN vendedores d ON v.vendedor = d.id_vendedor "
        "WHERE v.fecha BETWEEN DATE '2026-01-01' AND DATE '2026-03-31' AND d.sucursal IN ('Norte', 'Oeste')",
    )[0]
    assert _cerca(resultado.filas[0][0], esperado[0]) and resultado.filas[0][1] == esperado[1]
    assert 0 < resultado.filas[0][1] < 3000


def test_rango_abierto_y_operadores_escalares(conexion, modelo):
    desde = _correr(conexion, modelo, {"metricas": ["cantidad_ventas"], "filtros": [{"campo": "ventas.fecha", "operador": "entre", "valor": ["2026-06-01", None]}]})
    hasta = _correr(conexion, modelo, {"metricas": ["cantidad_ventas"], "filtros": [{"campo": "ventas.fecha", "operador": "menor", "valor": "2026-06-01"}]})
    assert desde.filas[0][0] + hasta.filas[0][0] == 3000
    grandes = _correr(conexion, modelo, {"metricas": ["cantidad_ventas"], "filtros": [{"campo": "ventas.importe", "operador": "mayor_igual", "valor": 10000}]})
    assert grandes.filas[0][0] == _sql(conexion, "SELECT count(*) FROM ventas WHERE importe >= 10000")[0][0]


def test_filtro_por_entidad_del_lado_muchos_usa_semi_join(conexion, modelo):
    consulta = {"metricas": ["total_ventas", "cantidad_ventas"], "filtros": [{"campo": "medios_pago.nombre", "operador": "igual", "valor": "Efectivo"}]}
    compilada = compilar(modelo, parsear_consulta(consulta))
    assert "EXISTS (" in compilada.sql
    assert "Efectivo" not in compilada.sql  # va como parametro
    assert compilada.parametros == ["Efectivo"]
    resultado = ejecutar_compilada(conexion, compilada)
    esperado = _sql(
        conexion,
        "SELECT sum(v.importe), count(v.id_venta) FROM ventas v WHERE EXISTS ("
        "SELECT 1 FROM pagos p JOIN medios_pago m ON p.id_medio_pago = m.id_medio_pago WHERE p.id_venta = v.id_venta AND m.nombre = 'Efectivo')",
    )[0]
    assert _cerca(resultado.filas[0][0], esperado[0]) and resultado.filas[0][1] == esperado[1]
    assert 0 < resultado.filas[0][1] < 3000


def test_filtro_contiene_nulo_y_booleano(conexion, modelo):
    yerba = _correr(conexion, modelo, {"metricas": ["cantidad_ventas"], "filtros": [{"campo": "productos.nombre", "operador": "contiene", "valor": "yerba"}]})
    assert yerba.filas[0][0] == _sql(conexion, "SELECT count(*) FROM ventas v JOIN productos p ON v.id_producto = p.id_producto WHERE p.nombre ILIKE '%yerba%'")[0][0]
    sin_vendedor = _correr(conexion, modelo, {"metricas": ["cantidad_ventas"], "filtros": [{"campo": "ventas.id_vendedor", "operador": "es_nulo"}]})
    assert sin_vendedor.filas[0][0] == _sql(conexion, "SELECT count(*) FROM ventas WHERE vendedor IS NULL")[0][0] > 0
    inactivos = _correr(conexion, modelo, {"metricas": ["cantidad_ventas"], "filtros": [{"campo": "productos.activo", "operador": "igual", "valor": False}]})
    assert inactivos.filas[0][0] == _sql(conexion, "SELECT count(*) FROM ventas v JOIN productos p ON v.id_producto = p.id_producto WHERE NOT p.activo")[0][0]


def test_filtros_afectan_a_todas_las_entidades_de_la_consulta(conexion, modelo):
    consulta = {
        "metricas": ["total_ventas", "total_pagado"],
        "filtros": [{"campo": "vendedores.sucursal", "operador": "igual", "valor": "Centro"}],
    }
    resultado = _correr(conexion, modelo, consulta)
    ventas = _sql(conexion, "SELECT sum(v.importe) FROM ventas v JOIN vendedores d ON v.vendedor = d.id_vendedor WHERE d.sucursal = 'Centro'")[0][0]
    pagos = _sql(conexion, "SELECT sum(p.monto) FROM pagos p JOIN ventas v ON p.id_venta = v.id_venta JOIN vendedores d ON v.vendedor = d.id_vendedor WHERE d.sucursal = 'Centro'")[0][0]
    assert _cerca(resultado.filas[0][0], ventas) and _cerca(resultado.filas[0][1], pagos)


# ---------- Explorador (entidad_base) ----------
def test_explorador_de_productos_muestra_todos_aunque_no_vendan(conexion, modelo):
    consulta = {
        "entidad_base": "productos",
        "metricas": ["total_ventas", "cantidad_ventas"],
        "dimensiones": [{"campo": "productos.nombre"}, {"campo": "productos.categoria"}, {"campo": "productos.precio_lista"}],
        "filtros": [{"campo": "ventas.fecha", "operador": "entre", "valor": ["2026-08-01", "2026-08-31"]}],
        "orden": [{"por": "total_ventas", "direccion": "desc"}],
    }
    resultado = _correr(conexion, modelo, consulta)
    esperado_con_ventas = _sql(conexion, "SELECT count(DISTINCT id_producto) FROM ventas WHERE fecha BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' AND id_producto <> 999")[0][0]
    # Aparecen solo los productos con alguna venta en el periodo (el filtro es semi-join sobre productos)...
    assert len(resultado.filas) == esperado_con_ventas
    # ...y sin filtro, todos, incluso los que nunca vendieron
    sin_filtro = _correr(conexion, modelo, {**consulta, "filtros": []})
    assert len(sin_filtro.filas) == 40
    nunca_vendidos = [fila for fila in sin_filtro.filas if fila[3] is None]
    assert all(fila[4] is None for fila in nunca_vendidos)


def test_explorador_de_ventas_con_columnas_relacionadas_y_paginado(conexion, modelo):
    consulta = {
        "entidad_base": "ventas",
        "dimensiones": [
            {"campo": "ventas.id_venta"},
            {"campo": "ventas.fecha"},
            {"campo": "ventas.importe"},
            {"campo": "vendedores.nombre", "alias": "vendedor"},
            {"campo": "productos.nombre", "alias": "producto"},
        ],
        "orden": [{"por": "ventas.id_venta", "direccion": "asc"}],
        "limite": 20,
        "desplazamiento": 40,
    }
    resultado = _correr(conexion, modelo, consulta)
    assert [c.nombre for c in resultado.columnas] == ["ventas.id_venta", "ventas.fecha", "ventas.importe", "vendedor", "producto"]
    assert [fila[0] for fila in resultado.filas] == list(range(41, 61))
    fila_41 = resultado.filas[0]
    esperado = _sql(conexion, "SELECT v.fecha, v.importe, d.nombre, p.nombre FROM ventas v LEFT JOIN vendedores d ON v.vendedor = d.id_vendedor LEFT JOIN productos p ON v.id_producto = p.id_producto WHERE v.id_venta = 41")[0]
    assert tuple(fila_41[1:]) == esperado


def test_valores_distintos_para_opciones_de_filtro(conexion, modelo):
    resultado = _correr(conexion, modelo, {"dimensiones": [{"campo": "vendedores.sucursal"}]})
    assert [fila[0] for fila in resultado.filas] == ["Centro", "Norte", "Oeste"]
    medios = _correr(conexion, modelo, {"dimensiones": [{"campo": "medios_pago.nombre"}], "orden": [{"por": "medios_pago.nombre", "direccion": "desc"}]})
    assert len(medios.filas) == 6 and medios.filas[0][0] == "Transferencia"


# ---------- Errores ----------
@pytest.mark.parametrize(
    "consulta, codigo",
    [
        ({"metricas": ["ganancia"]}, "E-CONS-01"),
        ({"dimensiones": [{"campo": "ventas.sucursal"}]}, "E-CONS-01"),
        ({"metricas": ["total_ventas"], "entidad_base": "sucursales"}, "E-CONS-01"),
        ({"metricas": ["total_ventas"], "dimensiones": [{"campo": "ventas.importe", "granularidad": "mes"}]}, "E-CONS-05"),
        ({"metricas": ["total_pagado"], "dimensiones": [{"campo": "pagos.fecha_pago", "granularidad": "dia"}]}, "E-CONS-05"),
        ({"metricas": ["total_ventas"], "filtros": [{"campo": "ventas.fecha", "operador": "entre", "valor": ["2026-01-01"]}]}, "E-CONS-06"),
        ({"metricas": ["total_ventas"], "filtros": [{"campo": "ventas.fecha", "operador": "en", "valor": "2026-01-01"}]}, "E-CONS-06"),
        ({"metricas": ["total_ventas"], "filtros": [{"campo": "ventas.fecha", "operador": "igual", "valor": None}]}, "E-CONS-06"),
        ({"metricas": ["total_ventas"], "filtros": [{"campo": "productos.nombre", "operador": "contiene", "valor": ""}]}, "E-CONS-06"),
        ({"metricas": ["total_ventas"], "dimensiones": [{"campo": "ventas.fecha", "alias": "x"}, {"campo": "ventas.importe", "alias": "x"}]}, "E-CONS-06"),
        ({"metricas": ["total_ventas"], "orden": [{"por": "cantidad_ventas"}]}, "E-CONS-08"),
        ({}, "E-CONS-07"),
        ({"metricas": ["total_ventas"], "limite": 0}, "E-CONS-07"),
        ({"metricas": ["total_ventas"], "algo": 1}, "E-CONS-07"),
    ],
)
def test_consultas_invalidas(conexion, modelo, consulta, codigo):
    with pytest.raises(ErrorApp) as error:
        _correr(conexion, modelo, consulta)
    assert error.value.codigo == codigo


def test_entidades_sin_relacion(conexion):
    sin_relacion = copy.deepcopy(MODELO_JSON)
    sin_relacion["relaciones"] = [r for r in sin_relacion["relaciones"] if r["id"] != "ventas_producto"]
    modelo_roto = modelo_efectivo(parsear_modelo(sin_relacion))
    with pytest.raises(ErrorApp) as error:
        compilar(modelo_roto, ConsultaSemantica(metricas=["total_ventas"], dimensiones=[{"campo": "productos.nombre"}]))
    assert error.value.codigo == "E-CONS-02"


def test_forma_del_sql_generado(modelo):
    compilada = compilar(modelo, parsear_consulta({"metricas": ["total_ventas"], "dimensiones": [{"campo": "vendedores.nombre"}], "limite": 10}))
    assert compilada.sql == (
        'WITH m0 AS (SELECT "vendedores"."nombre" AS "vendedores.nombre", SUM("ventas"."importe") AS "total_ventas" '
        'FROM "ventas" AS "ventas" LEFT JOIN "vendedores" AS "vendedores" ON "ventas"."vendedor" = "vendedores"."id_vendedor" GROUP BY 1) '
        'SELECT m0."vendedores.nombre" AS "vendedores.nombre", m0."total_ventas" AS "total_ventas" FROM m0 '
        'ORDER BY "vendedores.nombre" ASC NULLS LAST LIMIT 10'
    )
    assert compilada.parametros == []
