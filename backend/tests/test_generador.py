"""Generador determinista del spec base (paso 14): puro, sin base de datos."""
import json
from pathlib import Path

import duckdb
import pytest

from app.dashboard.generador import generar_spec_base
from app.dashboard.validacion import validar_spec
from app.inferencia.heuristicas import FuentePerfilada, proponer_modelo
from app.ingesta.procesador import ingestar_archivo
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo
from app.perfilado import PerfilFuente
from scripts.generar_datos_prueba import generar

DATOS_PRUEBA = Path(__file__).resolve().parents[1].parent / "datos_prueba"


@pytest.fixture(scope="module")
def modelo_a_mano() -> ModeloSemantico:
    contenido = json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))
    return modelo_efectivo(ModeloSemantico.model_validate(contenido))


@pytest.fixture(scope="module")
def modelo_heuristico(tmp_path_factory) -> ModeloSemantico:
    """El modelo propuesto por la heuristica (con evidencia real de
    cardinalidad), confirmando todo para que sea efectivo."""
    raiz = tmp_path_factory.mktemp("generador")
    conexion = duckdb.connect()
    fuentes = []
    for nombre, ruta in generar(raiz / "csv").items():
        directorio = raiz / f"ingesta_{nombre}"
        directorio.mkdir()
        resultado = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
        uri = resultado.ruta_parquet_temporal.as_posix()
        conexion.execute(f'CREATE VIEW "{resultado.nombre_tabla}" AS SELECT * FROM read_parquet(\'{uri}\')')
        fuentes.append(FuentePerfilada(resultado.nombre_tabla, resultado.esquema_como_dicts(), PerfilFuente.model_validate(resultado.perfil)))
    propuesta = proponer_modelo(conexion, fuentes)
    contenido = propuesta.model_dump()
    for entidad in contenido["entidades"]:
        for campo in entidad["campos"]:
            campo["estado"] = "confirmada"
    for relacion in contenido["relaciones"]:
        relacion["estado"] = "confirmada"
    for metrica in contenido["metricas"]:
        metrica["estado"] = "confirmada"
    return modelo_efectivo(ModeloSemantico.model_validate(contenido))


def test_spec_base_valido_sobre_el_modelo_a_mano(modelo_a_mano):
    spec = generar_spec_base(modelo_a_mano)
    assert validar_spec(spec, modelo_a_mano) == []
    assert spec.titulo is None  # lo pone Claude o queda sin titulo
    assert len(spec.kpis) == len(modelo_a_mano.metricas) == 8
    assert [kpi.metrica for kpi in spec.kpis] == [m.id for m in modelo_a_mano.metricas]
    assert {pestania.entidad for pestania in spec.explorador.pestanias} == {e.id for e in modelo_a_mano.entidades}


def test_ids_sin_colisiones_entre_entidades_con_el_mismo_campo(modelo_a_mano):
    spec = generar_spec_base(modelo_a_mano)
    ids = [f.id for f in spec.filtros] + [k.id for k in spec.kpis] + [g.id for g in spec.graficos]
    assert len(ids) == len(set(ids)), ids
    # vendedores.nombre y productos.nombre son dos campos "nombre": el segundo se desambigua
    ids_grafico_nombre = [g.id for g in spec.graficos if g.dimension.endswith(".nombre")]
    assert len(ids_grafico_nombre) == 2 and len(set(ids_grafico_nombre)) == 2


def test_linea_por_la_primera_dimension_de_tiempo_y_filtro_de_rango(modelo_a_mano):
    spec = generar_spec_base(modelo_a_mano)
    lineas = [g for g in spec.graficos if g.tipo == "linea"]
    assert len(lineas) == 1
    primera_dimension = modelo_a_mano.dimensiones_tiempo[0]
    assert lineas[0].dimension == primera_dimension.campo
    assert lineas[0].metrica == modelo_a_mano.metricas[0].id
    assert lineas[0].granularidad in primera_dimension.granularidades
    assert any(f.campo == primera_dimension.campo and f.tipo == "rango_fecha" for f in spec.filtros)


def test_hasta_tres_barras_por_categoria_con_su_filtro_lista(modelo_a_mano):
    spec = generar_spec_base(modelo_a_mano)
    barras = [g for g in spec.graficos if g.tipo == "barras"]
    assert len(barras) == 3  # el modelo a mano tiene mas de 3 campos categoria
    for grafico in barras:
        assert grafico.top == 10
        assert any(f.campo == grafico.dimension and f.tipo == "lista" for f in spec.filtros)


def test_ordena_las_categorias_por_cardinalidad_real_cuando_hay_evidencia(modelo_heuristico):
    """Con evidencia de verdad (modelo recien propuesto), la categoria con
    menos valores distintos entra primero: sucursal (3) antes que categoria
    de productos (6) o nombre de vendedor (12)."""
    spec = generar_spec_base(modelo_heuristico)
    barras = [g.dimension for g in spec.graficos if g.tipo == "barras"]
    assert barras[0] == "vendedores.sucursal", barras
    assert validar_spec(spec, modelo_heuristico) == []


def test_explorador_excluye_la_clave_primaria(modelo_a_mano):
    spec = generar_spec_base(modelo_a_mano)
    for entidad in modelo_a_mano.entidades:
        pestania = spec.pestania(entidad.id)
        assert pestania is not None
        assert not set(pestania.columnas) & set(entidad.clave_primaria)
        assert set(pestania.columnas) == {campo.id for campo in entidad.campos} - set(entidad.clave_primaria)


def test_sin_metricas_no_hay_kpis_ni_graficos_pero_el_explorador_sigue():
    modelo = ModeloSemantico.model_validate(
        {
            "entidades": [
                {
                    "id": "cosas",
                    "nombre": "Cosas",
                    "fuente": "cosas",
                    "tipo": "dimension",
                    "clave_primaria": ["id"],
                    "campos": [
                        {"id": "id", "columna_origen": "id", "nombre": "Id", "tipo_dato": "entero", "tipo_semantico": "identificador"},
                        {"id": "nombre", "columna_origen": "nombre", "nombre": "Nombre", "tipo_dato": "texto", "tipo_semantico": "categoria"},
                    ],
                }
            ]
        }
    )
    spec = generar_spec_base(modelo)
    assert spec.kpis == [] and spec.graficos == [] and spec.filtros == []
    assert spec.pestania("cosas").columnas == ["nombre"]
    assert validar_spec(spec, modelo) == []


def test_no_empareja_una_metrica_con_una_dimension_que_multiplicaria_filas():
    """Regresion: si la primera dimension de tiempo pertenece a una entidad
    'hija' (pagos) y la primera metrica a una entidad 'padre' (ventas), esa
    combinacion multiplicaria filas (E-CONS-04) y no tiene que proponerse.
    El generador tiene que probar otras metricas hasta encontrar una que sí
    funcione con esa dimension (aca, una metrica de la propia entidad pagos)."""
    contenido = {
        "entidades": [
            {
                "id": "ventas",
                "nombre": "Ventas",
                "fuente": "ventas",
                "tipo": "hechos",
                "clave_primaria": ["id_venta"],
                "campos": [
                    {"id": "id_venta", "columna_origen": "id_venta", "nombre": "Id venta", "tipo_dato": "entero", "tipo_semantico": "identificador"},
                    {"id": "importe", "columna_origen": "importe", "nombre": "Importe", "tipo_dato": "decimal", "tipo_semantico": "monto"},
                ],
            },
            {
                "id": "pagos",
                "nombre": "Pagos",
                "fuente": "pagos",
                "tipo": "hechos",
                "clave_primaria": ["id_pago"],
                "campos": [
                    {"id": "id_pago", "columna_origen": "id_pago", "nombre": "Id pago", "tipo_dato": "entero", "tipo_semantico": "identificador"},
                    {"id": "id_venta", "columna_origen": "id_venta", "nombre": "Venta", "tipo_dato": "entero", "tipo_semantico": "clave_foranea"},
                    {"id": "fecha_pago", "columna_origen": "fecha_pago", "nombre": "Fecha de pago", "tipo_dato": "fecha", "tipo_semantico": "fecha"},
                    {"id": "monto", "columna_origen": "monto", "nombre": "Monto", "tipo_dato": "decimal", "tipo_semantico": "monto"},
                ],
            },
        ],
        "relaciones": [
            {"id": "pagos_venta", "desde": {"entidad": "pagos", "campo": "id_venta"}, "hacia": {"entidad": "ventas", "campo": "id_venta"}, "cardinalidad": "n:1"}
        ],
        # A proposito en el orden "pagos, ventas": la primera metrica (total_pagado) es de pagos
        "metricas": [
            {"id": "total_pagado", "nombre": "Total pagado", "expresion": {"agregacion": "suma", "campo": "pagos.monto"}, "formato": "moneda"},
            {"id": "total_ventas", "nombre": "Total ventas", "expresion": {"agregacion": "suma", "campo": "ventas.importe"}, "formato": "moneda"},
        ],
        # Y la primera dimension de tiempo es justamente la de pagos: emparejarla
        # con una metrica de ventas multiplicaria filas (ventas -> pagos es 1:n)
        "dimensiones_tiempo": [{"campo": "pagos.fecha_pago", "granularidades": ["mes"]}],
    }
    modelo = modelo_efectivo(ModeloSemantico.model_validate(contenido))
    spec = generar_spec_base(modelo)
    assert validar_spec(spec, modelo) == []
    lineas = [g for g in spec.graficos if g.tipo == "linea"]
    assert len(lineas) == 1 and lineas[0].metrica == "total_pagado", "total_ventas no podia usarse: se eligio la que sí compila"
