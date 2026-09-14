"""Reporte de calidad de datos (fase 4): puro, DuckDB en memoria, sin
Postgres — mismo criterio que los tests del compilador."""
import duckdb
import pytest

from app.calidad.analisis import calcular_reporte
from app.modelo.esquema import Campo, Entidad, ExtremoRelacion, ModeloSemantico, Relacion


def _literal(valor) -> str:
    if valor is None:
        return "NULL"
    if isinstance(valor, str):
        return "'" + valor.replace("'", "''") + "'"
    return str(valor)


def _tabla(conexion: duckdb.DuckDBPyConnection, nombre: str, columnas: list[str], filas: list[tuple]) -> None:
    cols = ", ".join(columnas)
    valores = ", ".join("(" + ", ".join(_literal(valor) for valor in fila) + ")" for fila in filas)
    conexion.execute(f'CREATE TABLE "{nombre}" AS SELECT * FROM (VALUES {valores}) AS t({cols})')


def _perfil(filas: int, columnas: list[dict]) -> dict:
    return {
        "nombre_tabla": "ventas",
        "filas": filas,
        "candidatas_clave": [],
        "columnas": [{"distintos": 0, "unica": False, **columna} for columna in columnas],
    }


@pytest.fixture
def conexion():
    con = duckdb.connect()
    yield con
    con.close()


def test_detecta_nulos_altos(conexion):
    _tabla(conexion, "ventas", ["id", "vendedor"], [(1, "Ana"), (2, None), (3, None), (4, None)])
    perfil = _perfil(4, [{"nombre": "id", "tipo": "entero", "nulos": 0}, {"nombre": "vendedor", "tipo": "texto", "nulos": 3}])
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}, {"nombre": "vendedor", "tipo": "texto", "invalidos": 0}]
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=4, perfil=perfil, modelo=None)
    problema = next(p for p in reporte.problemas if p.codigo == "nulos_altos")
    assert problema.campo == "vendedor"
    assert problema.severidad == "alta"  # 75% >= 50%


def test_nulos_moderados_son_severidad_media(conexion):
    _tabla(conexion, "ventas", ["id", "sucursal"], [(1, "Centro"), (2, "Centro"), (3, None), (4, "Centro")])
    perfil = _perfil(4, [{"nombre": "id", "tipo": "entero", "nulos": 0}, {"nombre": "sucursal", "tipo": "texto", "nulos": 1}])
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}, {"nombre": "sucursal", "tipo": "texto", "invalidos": 0}]
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=4, perfil=perfil, modelo=None)
    problema = next(p for p in reporte.problemas if p.codigo == "nulos_altos")
    assert problema.severidad == "media"  # 25%: por encima del umbral (20%) pero lejos de "alta"


def test_pocos_nulos_no_generan_problema(conexion):
    _tabla(conexion, "ventas", ["id"], [(1,), (2,), (3,), (4,), (5,)])
    perfil = _perfil(5, [{"nombre": "id", "tipo": "entero", "nulos": 0}])
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}]
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=5, perfil=perfil, modelo=None)
    assert reporte.problemas == []


def test_detecta_valores_invalidos(conexion):
    _tabla(conexion, "ventas", ["id", "importe"], [(1, 10.5), (2, None), (3, 20.0), (4, None)])
    perfil = _perfil(4, [{"nombre": "id", "tipo": "entero", "nulos": 0}, {"nombre": "importe", "tipo": "decimal", "nulos": 2}])
    # 2 de los nulos de "importe" son porque el dato original no se pudo tipear (invalidos), no porque venian vacios
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}, {"nombre": "importe", "tipo": "decimal", "invalidos": 2}]
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=4, perfil=perfil, modelo=None)
    problema = next(p for p in reporte.problemas if p.codigo == "valores_invalidos")
    assert problema.campo == "importe" and problema.detalle["invalidos"] == 2


def test_detecta_filas_duplicadas(conexion):
    _tabla(conexion, "ventas", ["id", "importe"], [(1, 10.5), (1, 10.5), (2, 20.0)])
    perfil = _perfil(3, [{"nombre": "id", "tipo": "entero", "nulos": 0}, {"nombre": "importe", "tipo": "decimal", "nulos": 0}])
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}, {"nombre": "importe", "tipo": "decimal", "invalidos": 0}]
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=3, perfil=perfil, modelo=None)
    problema = next(p for p in reporte.problemas if p.codigo == "filas_duplicadas")
    assert problema.detalle["duplicados"] == 1  # 2 filas identicas = 1 "de mas"


def test_sin_modelo_no_chequea_clave_ni_huerfanos(conexion):
    _tabla(conexion, "ventas", ["id"], [(1,), (1,)])  # clave "rota", pero sin modelo no hay como saberlo
    perfil = _perfil(2, [{"nombre": "id", "tipo": "entero", "nulos": 0}])
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}]
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=2, perfil=perfil, modelo=None)
    assert all(p.codigo not in ("clave_no_unica", "huerfanos") for p in reporte.problemas)


def _campo(id_campo: str, columna_origen: str, tipo_dato: str = "entero", tipo_semantico: str = "identificador") -> Campo:
    return Campo(id=id_campo, columna_origen=columna_origen, nombre=id_campo, tipo_dato=tipo_dato, tipo_semantico=tipo_semantico)


def test_detecta_clave_primaria_no_unica(conexion):
    _tabla(conexion, "ventas", ["id_venta"], [(1,), (1,), (2,)])
    perfil = _perfil(3, [{"nombre": "id_venta", "tipo": "entero", "nulos": 0}])
    esquema = [{"nombre": "id_venta", "tipo": "entero", "invalidos": 0}]
    modelo = ModeloSemantico(
        entidades=[Entidad(id="ventas", nombre="Ventas", fuente="ventas", tipo="hechos", clave_primaria=["id_venta"], campos=[_campo("id_venta", "id_venta")])]
    )
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=3, perfil=perfil, modelo=modelo)
    problema = next(p for p in reporte.problemas if p.codigo == "clave_no_unica")
    assert problema.severidad == "alta" and problema.detalle["duplicados"] == 1


def test_clave_primaria_unica_no_genera_problema(conexion):
    _tabla(conexion, "ventas", ["id_venta"], [(1,), (2,), (3,)])
    perfil = _perfil(3, [{"nombre": "id_venta", "tipo": "entero", "nulos": 0}])
    esquema = [{"nombre": "id_venta", "tipo": "entero", "invalidos": 0}]
    modelo = ModeloSemantico(
        entidades=[Entidad(id="ventas", nombre="Ventas", fuente="ventas", tipo="hechos", clave_primaria=["id_venta"], campos=[_campo("id_venta", "id_venta")])]
    )
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=3, perfil=perfil, modelo=modelo)
    assert all(p.codigo != "clave_no_unica" for p in reporte.problemas)


def test_detecta_huerfanos_en_relacion_confirmada(conexion):
    _tabla(conexion, "ventas", ["id_venta", "id_vendedor"], [(1, 1), (2, 1), (3, 99)])  # 99 no existe en vendedores
    _tabla(conexion, "vendedores", ["id_vendedor"], [(1,), (2,)])
    perfil = _perfil(3, [{"nombre": "id_venta", "tipo": "entero", "nulos": 0}, {"nombre": "id_vendedor", "tipo": "entero", "nulos": 0}])
    esquema = [{"nombre": "id_venta", "tipo": "entero", "invalidos": 0}, {"nombre": "id_vendedor", "tipo": "entero", "invalidos": 0}]
    modelo = ModeloSemantico(
        entidades=[
            Entidad(
                id="ventas", nombre="Ventas", fuente="ventas", tipo="hechos", clave_primaria=["id_venta"],
                campos=[_campo("id_venta", "id_venta"), _campo("id_vendedor", "id_vendedor", tipo_semantico="clave_foranea")],
            ),
            Entidad(id="vendedores", nombre="Vendedores", fuente="vendedores", tipo="dimension", clave_primaria=["id_vendedor"], campos=[_campo("id_vendedor", "id_vendedor")]),
        ],
        relaciones=[Relacion(id="r1", desde=ExtremoRelacion(entidad="ventas", campo="id_vendedor"), hacia=ExtremoRelacion(entidad="vendedores", campo="id_vendedor"))],
    )
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=3, perfil=perfil, modelo=modelo)
    problema = next(p for p in reporte.problemas if p.codigo == "huerfanos")
    assert problema.detalle["huerfanos"] == 1 and problema.detalle["hacia"] == "vendedores"


def test_relacion_propuesta_no_confirmada_no_se_chequea(conexion):
    _tabla(conexion, "ventas", ["id_venta", "id_vendedor"], [(1, 99)])
    _tabla(conexion, "vendedores", ["id_vendedor"], [(1,)])
    perfil = _perfil(1, [{"nombre": "id_venta", "tipo": "entero", "nulos": 0}, {"nombre": "id_vendedor", "tipo": "entero", "nulos": 0}])
    esquema = [{"nombre": "id_venta", "tipo": "entero", "invalidos": 0}, {"nombre": "id_vendedor", "tipo": "entero", "invalidos": 0}]
    modelo = ModeloSemantico(
        entidades=[
            Entidad(id="ventas", nombre="Ventas", fuente="ventas", tipo="hechos", clave_primaria=["id_venta"], campos=[_campo("id_venta", "id_venta"), _campo("id_vendedor", "id_vendedor")]),
            Entidad(id="vendedores", nombre="Vendedores", fuente="vendedores", tipo="dimension", clave_primaria=["id_vendedor"], campos=[_campo("id_vendedor", "id_vendedor")]),
        ],
        relaciones=[Relacion(id="r1", desde=ExtremoRelacion(entidad="ventas", campo="id_vendedor"), hacia=ExtremoRelacion(entidad="vendedores", campo="id_vendedor"), estado="propuesta")],
    )
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=1, perfil=perfil, modelo=modelo)
    assert all(p.codigo != "huerfanos" for p in reporte.problemas)


def test_orden_por_severidad(conexion):
    _tabla(conexion, "ventas", ["id", "sucursal"], [(1, "Centro"), (1, "Centro"), (2, None)])
    perfil = _perfil(3, [{"nombre": "id", "tipo": "entero", "nulos": 0}, {"nombre": "sucursal", "tipo": "texto", "nulos": 1}])
    esquema = [{"nombre": "id", "tipo": "entero", "invalidos": 0}, {"nombre": "sucursal", "tipo": "texto", "invalidos": 0}]
    modelo = ModeloSemantico(
        entidades=[Entidad(id="ventas", nombre="Ventas", fuente="ventas", tipo="hechos", clave_primaria=["id"], campos=[_campo("id", "id")])]
    )
    reporte = calcular_reporte(conexion, nombre_tabla="ventas", esquema=esquema, filas=3, perfil=perfil, modelo=modelo)
    severidades = [problema.severidad for problema in reporte.problemas]
    assert severidades.index("alta") < severidades.index("media")  # clave_no_unica antes que filas_duplicadas/nulos_altos
