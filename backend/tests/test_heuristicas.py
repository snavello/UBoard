"""Heuristicas de inferencia contra los 5 CSV sinteticos (puro: DuckDB en
memoria, sin Postgres). Criterio de aceptacion de la fase 2: las 4 relaciones
y las 5 claves primarias del modelo escrito a mano, sin intervencion."""
import json
from pathlib import Path

import duckdb
import pytest

from app.inferencia.heuristicas import (
    FuentePerfilada,
    elegir_clave_primaria,
    parece_clave,
    parece_medida,
    proponer_modelo,
    similitud_nombre,
    tipo_semantico_de,
)
from app.ingesta.procesador import ingestar_archivo
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo, validar_estructura
from app.perfilado import PerfilColumna, PerfilFuente
from scripts.generar_datos_prueba import generar

DATOS_PRUEBA = Path(__file__).resolve().parents[1].parent / "datos_prueba"


@pytest.fixture(scope="module")
def propuesta(tmp_path_factory) -> ModeloSemantico:
    raiz = tmp_path_factory.mktemp("heuristicas")
    conexion = duckdb.connect()
    fuentes = []
    for nombre, ruta in generar(raiz / "csv").items():
        directorio = raiz / f"ingesta_{nombre}"
        directorio.mkdir()
        resultado = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
        uri = resultado.ruta_parquet_temporal.as_posix()
        conexion.execute(f'CREATE VIEW "{resultado.nombre_tabla}" AS SELECT * FROM read_parquet(\'{uri}\')')
        fuentes.append(FuentePerfilada(resultado.nombre_tabla, resultado.esquema_como_dicts(), PerfilFuente.model_validate(resultado.perfil)))
    return proponer_modelo(conexion, fuentes)


@pytest.fixture(scope="module")
def modelo_a_mano() -> ModeloSemantico:
    return ModeloSemantico.model_validate(json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8")))


def test_la_propuesta_es_un_modelo_valido(propuesta):
    assert validar_estructura(propuesta) == []
    assert [entidad.id for entidad in propuesta.entidades] == ["medios_pago", "pagos", "productos", "vendedores", "ventas"]


def test_aceptacion_claves_primarias_5_de_5(propuesta, modelo_a_mano):
    esperadas = {entidad.id: entidad.clave_primaria for entidad in modelo_a_mano.entidades}
    for entidad in propuesta.entidades:
        assert entidad.clave_primaria == esperadas[entidad.id], entidad.id
        clave = entidad.campo(entidad.clave_primaria[0])
        assert clave.estado == "confirmada" and clave.tipo_semantico == "identificador"
        assert clave.confianza >= 0.95, (entidad.id, clave.evidencia)
    # Donde `nombre` tambien era unica, el id gano por nombre
    productos = propuesta.entidad("productos").campo("id_producto")
    assert productos.evidencia["motivo"] == "varias_candidatas_una_con_nombre_de_clave"
    assert productos.evidencia["candidatas"] == ["id_producto", "nombre"]


def test_aceptacion_relaciones_4_de_4_sin_intervencion(propuesta, modelo_a_mano):
    # El modelo a mano llama `id_vendedor` al campo cuya columna es `vendedor`
    columna = {
        f"{entidad.id}.{campo.id}": f"{entidad.id}.{campo.columna_origen}"
        for entidad in modelo_a_mano.entidades
        for campo in entidad.campos
    }
    esperadas = {(columna[relacion.desde.referencia], columna[relacion.hacia.referencia]) for relacion in modelo_a_mano.relaciones}
    efectivas = {
        (relacion.desde.referencia, relacion.hacia.referencia) for relacion in modelo_efectivo(propuesta).relaciones
    }
    assert efectivas == esperadas
    assert len(propuesta.relaciones) == 4, [(r.desde.referencia, r.hacia.referencia, r.confianza) for r in propuesta.relaciones]
    for relacion in propuesta.relaciones:
        assert relacion.estado == "propuesta" and relacion.origen_es_heuristica if hasattr(relacion, "origen_es_heuristica") else True
        assert relacion.cardinalidad == "n:1"
        assert relacion.evidencia["nombre_similar"] is True
        assert relacion.evidencia["inclusion"] >= 0.95


def test_la_evidencia_muestra_los_huerfanos(propuesta):
    vendedor = next(r for r in propuesta.relaciones if r.desde.referencia == "ventas.vendedor")
    assert vendedor.hacia.referencia == "vendedores.id_vendedor"
    assert vendedor.evidencia["huerfanos"] > 0, "2 % de ventas con vendedor 99"
    assert vendedor.evidencia["nulos"] > 0, "3 % de ventas sin vendedor"
    assert vendedor.evidencia["inclusion_distintos"] < 0.95 < vendedor.evidencia["inclusion"], "por filas pasa, por distintos no"
    assert vendedor.confianza == 0.9
    medio = next(r for r in propuesta.relaciones if r.desde.referencia == "pagos.id_medio_pago")
    assert medio.evidencia["huerfanos"] == 0 and medio.confianza == 0.95


def test_tipos_de_entidad_y_semanticos_como_el_modelo_a_mano(propuesta, modelo_a_mano):
    tipos_entidad = {entidad.id: entidad.tipo for entidad in modelo_a_mano.entidades}
    for entidad in propuesta.entidades:
        assert entidad.tipo == tipos_entidad[entidad.id], entidad.id
    esperados = {
        f"{entidad.id}.{campo.columna_origen}": campo.tipo_semantico for entidad in modelo_a_mano.entidades for campo in entidad.campos
    }
    for entidad in propuesta.entidades:
        for campo in entidad.campos:
            assert campo.tipo_semantico == esperados[f"{entidad.id}.{campo.columna_origen}"], (entidad.id, campo.id, campo.evidencia)
            assert campo.origen == "heuristica"
            assert campo.estado == ("confirmada" if campo.id in entidad.clave_primaria else "propuesta")
            assert "nulos" in campo.evidencia and "distintos" in campo.evidencia


def test_metricas_obvias_y_dimensiones_de_tiempo(propuesta):
    ids = {metrica.id: metrica for metrica in propuesta.metricas}
    assert {"cantidad_ventas", "total_importe", "cantidad_pagos", "total_monto"} <= set(ids)
    assert "total_precio_unitario" not in ids, "sumar precios unitarios no es una metrica"
    assert ids["total_importe"].expresion.agregacion == "suma" and ids["total_importe"].formato == "moneda"
    assert ids["cantidad_ventas"].expresion.campo == "ventas.id_venta" and ids["cantidad_ventas"].formato == "entero"
    assert all(metrica.estado == "propuesta" and metrica.origen == "heuristica" for metrica in propuesta.metricas)
    # Propuestas no entran al modelo efectivo hasta que alguien las confirme
    assert modelo_efectivo(propuesta).metricas == []
    assert [dimension.campo for dimension in propuesta.dimensiones_tiempo] == ["pagos.fecha_pago", "ventas.fecha"]


# ---------- Piezas ----------
def test_similitud_de_nombres():
    assert similitud_nombre("vendedor", "vendedores", "id_vendedor") >= 0.9
    assert similitud_nombre("id_producto", "productos", "id_producto") == 1.0
    assert similitud_nombre("id_medio_pago", "medios_pago", "id_medio_pago") >= 0.9
    assert similitud_nombre("cantidad", "vendedores", "id_vendedor") < 0.8
    assert similitud_nombre("cuotas", "productos", "id_producto") < 0.8


def test_parece_clave_y_parece_medida():
    assert parece_clave("id_venta") and parece_clave("codigo_cliente") and parece_clave("idcliente")
    assert not parece_clave("cantidad") and not parece_clave("importe")
    assert parece_medida("cantidad") and parece_medida("importe_neto") and parece_medida("porc_descuento")
    assert not parece_medida("sucursal")


def _perfil(nombre: str, tipo: str, **extra) -> PerfilColumna:
    base = {"nombre": nombre, "tipo": tipo, "nulos": 0, "distintos": 10, "unica": False}
    return PerfilColumna(**{**base, **extra})


def test_tipos_semanticos_por_patron():
    def tipo(nombre, tipo_dato, filas=1000, **extra):
        return tipo_semantico_de(nombre, tipo_dato, _perfil(nombre, tipo_dato, **extra), filas, es_pk=False, confianza_fk=None)[0]

    assert tipo("porc_descuento", "decimal") == "porcentaje"
    assert tipo("importe_neto", "decimal") == "monto"
    assert tipo("ratio", "decimal", minimo=0.1, maximo=0.9) == "porcentaje"
    assert tipo("x", "decimal", minimo=5, maximo=900) == "monto"
    assert tipo("unidades", "entero") == "cantidad"
    assert tipo("anio", "entero", distintos=5) == "categoria", "un entero con pocos valores distintos es categoria"
    assert tipo("edad", "entero", distintos=60) == "cantidad"
    assert tipo("provincia", "texto") == "geo"
    assert tipo("email", "texto", patron="email") == "texto_libre"
    assert tipo("sucursal", "texto", distintos=3) == "categoria"
    assert tipo("observaciones", "texto", distintos=900) == "texto_libre"
    assert tipo("codigo_postal", "texto", distintos=400, patron="numerico") == "categoria"
    assert tipo("cuando", "fecha") == "fecha" and tipo("activo", "booleano") == "booleano"
    # Lo dudoso queda con 0.6 para que Claude opine
    assert tipo_semantico_de("x", "decimal", _perfil("x", "decimal", minimo=5, maximo=900), 1000, es_pk=False, confianza_fk=None)[1] == 0.6


def test_eleccion_de_clave_primaria():
    def fuente(candidatas, esquema=("a", "b")):
        perfil = PerfilFuente(nombre_tabla="clientes", filas=3, columnas=[], candidatas_clave=list(candidatas))
        return FuentePerfilada("clientes", [{"nombre": nombre, "tipo": "texto"} for nombre in esquema], perfil)

    assert elegir_clave_primaria(fuente(["cuit"]))[:2] == ("cuit", 0.98)
    assert elegir_clave_primaria(fuente(["nombre", "id_cliente"]))[:2] == ("id_cliente", 0.95)
    assert elegir_clave_primaria(fuente(["nombre", "cliente"]))[:2] == ("cliente", 0.95)  # raiz igual a la tabla
    assert elegir_clave_primaria(fuente(["nombre", "email"]))[:2] == ("nombre", 0.85)
    clave, confianza, evidencia = elegir_clave_primaria(fuente([]))
    assert (clave, confianza, evidencia["motivo"]) == ("a", 0.3, "sin_candidata")


def test_dos_destinos_posibles_solo_uno_entra_y_el_otro_baja_a_0_89():
    """Una columna `id_cliente` que calza al 100 % con dos tablas de nombre
    parecido: la mejor entra, la otra queda propuesta en 0.89."""
    conexion = duckdb.connect()
    conexion.execute("CREATE TABLE pedidos AS SELECT * FROM (VALUES (1, 1), (2, 2), (3, 1)) AS v(id_pedido, id_cliente)")
    conexion.execute("CREATE TABLE clientes AS SELECT * FROM (VALUES (1, 'a'), (2, 'b')) AS v(id_cliente, nombre)")
    conexion.execute("CREATE TABLE clientes_vip AS SELECT * FROM (VALUES (1, 'a'), (2, 'b'), (3, 'c')) AS v(id_cliente, nivel)")

    def perfilada(tabla, columnas):
        from app.perfilado import perfilar

        esquema = [{"nombre": nombre, "tipo": tipo} for nombre, tipo in columnas]
        return FuentePerfilada(tabla, esquema, perfilar(conexion, tabla, tabla, columnas))

    modelo = proponer_modelo(
        conexion,
        [
            perfilada("pedidos", [("id_pedido", "entero"), ("id_cliente", "entero")]),
            perfilada("clientes", [("id_cliente", "entero"), ("nombre", "texto")]),
            perfilada("clientes_vip", [("id_cliente", "entero"), ("nivel", "texto")]),
        ],
    )
    assert validar_estructura(modelo) == []
    relaciones = sorted(modelo.relaciones, key=lambda r: -r.confianza)
    assert [(r.hacia.entidad, r.confianza) for r in relaciones] == [("clientes", 0.95), ("clientes_vip", 0.89)]
    assert relaciones[1].evidencia["bajada_por"] == "otra_relacion_mas_confiable_para_la_columna"
    assert len(modelo_efectivo(modelo).relaciones) == 1
    assert modelo.entidad("pedidos").tipo == "hechos" and modelo.entidad("clientes").tipo == "dimension"
