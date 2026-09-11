"""Esquema y validacion del modelo semantico. Puro: el modelo a mano de
datos_prueba/modelo.json contra los esquemas reales de los 5 CSV sinteticos."""
import copy
import json

import pytest

from app.ingesta.procesador import ingestar_archivo
from app.modelo import validacion
from app.modelo.esquema import ModeloSemantico
from app.modelo.operaciones import calcular_diff
from app.modelo.validacion import (
    modelo_efectivo,
    parsear_modelo,
    validar_contra_fuentes,
    validar_estructura,
)
from app.nucleo.errores import ErrorApp
from tests.conftest import ARCHIVOS_PRUEBA, DATOS_PRUEBA

MODELO_BASE = json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))


@pytest.fixture
def modelo() -> dict:
    return copy.deepcopy(MODELO_BASE)


@pytest.fixture(scope="module")
def esquemas_prueba(tmp_path_factory) -> dict:
    """nombre_tabla -> esquema, ingestando los 5 CSV commiteados."""
    esquemas = {}
    for nombre in ARCHIVOS_PRUEBA:
        directorio = tmp_path_factory.mktemp(nombre.replace(".", "_"))
        resultado = ingestar_archivo((DATOS_PRUEBA / nombre).read_bytes(), nombre, directorio)[0]
        esquemas[resultado.nombre_tabla] = resultado.esquema_como_dicts()
    return esquemas


def _codigos(errores: list[validacion.ErrorValidacion]) -> list[str]:
    return [error.codigo for error in errores]


def _entidad(modelo: dict, entidad_id: str) -> dict:
    return next(entidad for entidad in modelo["entidades"] if entidad["id"] == entidad_id)


def _campo(modelo: dict, entidad_id: str, campo_id: str) -> dict:
    return next(campo for campo in _entidad(modelo, entidad_id)["campos"] if campo["id"] == campo_id)


def _metrica(modelo: dict, metrica_id: str) -> dict:
    return next(metrica for metrica in modelo["metricas"] if metrica["id"] == metrica_id)


def _errores(modelo: dict) -> list[str]:
    return _codigos(validar_estructura(parsear_modelo(modelo)))


# ---------- El modelo a mano es valido ----------
def test_el_modelo_a_mano_es_valido_y_coincide_con_las_fuentes(modelo, esquemas_prueba):
    parseado = parsear_modelo(modelo)
    assert validar_estructura(parseado) == []
    assert validar_contra_fuentes(parseado, esquemas_prueba) == []
    assert parseado.resumen() == "5 entidades, 4 relaciones, 8 métricas, 2 dimensiones de tiempo"
    # Todo confirmado: el modelo efectivo es el mismo
    assert modelo_efectivo(parseado) == parseado


def test_defaults_de_campos_y_metricas(modelo):
    parseado = parsear_modelo(modelo)
    campo = parseado.resolver_campo("ventas.importe")[1]
    assert (campo.confianza, campo.origen, campo.estado) == (1.0, "usuario", "confirmada")
    assert parseado.metrica("ticket_promedio").expresion.numerador == "total_ventas"
    assert parseado.resolver_campo("ventas.no_existe") is None
    assert parseado.resolver_campo("nada.fecha") is None


# ---------- Esquema (Pydantic) ----------
def test_clave_desconocida_falla_al_parsear(modelo):
    modelo["entidades"][0]["fuente_id"] = "src_01"
    with pytest.raises(ErrorApp) as error:
        parsear_modelo(modelo)
    assert error.value.codigo == "E-MOD-01"
    errores = error.value.extra["errores"]
    assert errores[0]["codigo"] == validacion.JSON_INVALIDO
    assert errores[0]["ubicacion"] == "entidades.0.fuente_id"


@pytest.mark.parametrize("id_invalido", ["Ventas", "1ventas", "ventas-2026", "ñoquis", ""])
def test_los_ids_son_identificadores_en_minusculas(modelo, id_invalido):
    modelo["entidades"][0]["id"] = id_invalido
    with pytest.raises(ErrorApp):
        parsear_modelo(modelo)


def test_referencia_de_campo_con_formato_entidad_punto_campo(modelo):
    _metrica(modelo, "total_ventas")["expresion"]["campo"] = "importe"
    with pytest.raises(ErrorApp):
        parsear_modelo(modelo)


def test_expresion_ni_agregacion_ni_cociente(modelo):
    _metrica(modelo, "total_ventas")["expresion"] = {"formula": "a / b"}
    with pytest.raises(ErrorApp):
        parsear_modelo(modelo)


# ---------- Ids y claves ----------
def test_ids_duplicados(modelo):
    modelo["entidades"].append(copy.deepcopy(_entidad(modelo, "vendedores")))
    _entidad(modelo, "ventas")["campos"].append(copy.deepcopy(_campo(modelo, "ventas", "fecha")))
    modelo["metricas"].append(copy.deepcopy(_metrica(modelo, "total_ventas")))
    modelo["relaciones"].append(copy.deepcopy(modelo["relaciones"][0]))
    errores = validar_estructura(parsear_modelo(modelo))
    assert _codigos(errores).count(validacion.ID_DUPLICADO) == 4


def test_clave_primaria_inexistente_o_sin_confirmar(modelo):
    _entidad(modelo, "ventas")["clave_primaria"] = ["id_ticket"]
    assert validacion.PK_INEXISTENTE in _errores(modelo)

    modelo = copy.deepcopy(MODELO_BASE)
    _campo(modelo, "ventas", "id_venta")["estado"] = "propuesta"
    assert validacion.PK_NO_CONFIRMADA in _errores(modelo)


# ---------- Relaciones ----------
def test_relacion_a_entidad_o_campo_inexistente(modelo):
    modelo["relaciones"][0]["hacia"]["entidad"] = "sucursales"
    assert _errores(modelo) == [validacion.REL_ENTIDAD]
    modelo["relaciones"][0]["hacia"] = {"entidad": "vendedores", "campo": "legajo"}
    assert _errores(modelo) == [validacion.REL_CAMPO]


def test_relacion_consigo_misma(modelo):
    modelo["relaciones"][0]["hacia"] = {"entidad": "ventas", "campo": "id_venta"}
    assert _errores(modelo) == [validacion.REL_MISMA_ENTIDAD]


def test_el_destino_de_una_n_a_1_tiene_que_ser_clave_primaria(modelo):
    modelo["relaciones"][0]["hacia"]["campo"] = "nombre"
    errores = _errores(modelo)
    assert validacion.REL_NO_PK in errores
    assert validacion.REL_TIPOS in errores  # entero vs texto, ademas


def test_relacion_1_a_n_exige_pk_en_el_origen(modelo):
    modelo["relaciones"][0]["cardinalidad"] = "1:n"  # ventas.id_vendedor no es PK de ventas
    assert validacion.REL_NO_PK in _errores(modelo)


def test_relacion_entre_tipos_distintos(modelo):
    _campo(modelo, "ventas", "id_vendedor")["tipo_dato"] = "texto"
    assert _errores(modelo) == [validacion.REL_TIPOS]


def test_dos_relaciones_entre_las_mismas_entidades(modelo):
    modelo["relaciones"].append(
        {"id": "otra", "desde": {"entidad": "ventas", "campo": "id_producto"}, "hacia": {"entidad": "vendedores", "campo": "id_vendedor"}}
    )
    assert _errores(modelo) == [validacion.REL_DUPLICADA]


def test_ciclo_de_relaciones(modelo):
    # vendedores -> productos cierra el ciclo ventas-vendedores-productos
    modelo["relaciones"].append(
        {"id": "vendedor_producto", "desde": {"entidad": "vendedores", "campo": "id_vendedor"}, "hacia": {"entidad": "productos", "campo": "id_producto"}}
    )
    errores = validar_estructura(parsear_modelo(modelo))
    assert _codigos(errores) == [validacion.REL_CICLO]
    assert "productos" in errores[0].mensaje and "vendedores" in errores[0].mensaje and "ventas" in errores[0].mensaje


def test_una_relacion_rechazada_rompe_el_ciclo(modelo):
    modelo["relaciones"].append(
        {"id": "vendedor_producto", "desde": {"entidad": "vendedores", "campo": "id_vendedor"}, "hacia": {"entidad": "productos", "campo": "id_producto"}, "estado": "rechazada"}
    )
    assert _errores(modelo) == []
    assert len(modelo_efectivo(parsear_modelo(modelo)).relaciones) == 4


def test_relacion_confirmada_sobre_campo_rechazado(modelo):
    _campo(modelo, "ventas", "id_vendedor")["estado"] = "rechazada"
    errores = _errores(modelo)
    assert validacion.REL_CAMPO_NO_EFECTIVO in errores
    assert validacion.MET_CAMPO_NO_EFECTIVO in errores  # vendedores_activos cuenta ese campo


# ---------- Metricas ----------
def test_metrica_sobre_campo_inexistente(modelo):
    _metrica(modelo, "total_ventas")["expresion"]["campo"] = "ventas.total"
    errores = validar_estructura(parsear_modelo(modelo))
    assert errores[0].codigo == validacion.MET_CAMPO
    assert errores[0].ubicacion == "metricas.total_ventas"
    # Y arrastra al cociente que la usa: ticket_promedio queda sin numerador efectivo
    assert [error.codigo for error in errores[1:]] == [validacion.MET_CAMPO_NO_EFECTIVO]
    assert errores[1].ubicacion == "metricas.ticket_promedio"


def test_suma_de_texto_y_minimo_de_booleano(modelo):
    _metrica(modelo, "total_ventas")["expresion"]["campo"] = "vendedores.nombre"
    _metrica(modelo, "unidades_vendidas")["expresion"] = {"agregacion": "minimo", "campo": "productos.activo"}
    assert _errores(modelo) == [validacion.MET_AGREGACION, validacion.MET_AGREGACION]


def test_conteo_y_minimo_aceptan_cualquier_tipo_razonable(modelo):
    _metrica(modelo, "cantidad_ventas")["expresion"] = {"agregacion": "conteo_distinto", "campo": "vendedores.nombre"}
    _metrica(modelo, "unidades_vendidas")["expresion"] = {"agregacion": "maximo", "campo": "ventas.fecha"}
    assert _errores(modelo) == []


def test_cociente_invalido(modelo):
    ticket = _metrica(modelo, "ticket_promedio")
    ticket["expresion"] = {"numerador": "ticket_promedio", "denominador": "no_existe"}
    assert _errores(modelo) == [validacion.MET_COCIENTE, validacion.MET_COCIENTE]

    modelo = copy.deepcopy(MODELO_BASE)
    modelo["metricas"].append({"id": "anidado", "nombre": "Anidado", "expresion": {"numerador": "ticket_promedio", "denominador": "cantidad_ventas"}})
    assert _errores(modelo) == [validacion.MET_COCIENTE]


def test_cociente_confirmado_sobre_metrica_propuesta(modelo):
    _metrica(modelo, "cantidad_ventas")["estado"] = "propuesta"
    assert _errores(modelo) == [validacion.MET_CAMPO_NO_EFECTIVO]


# ---------- Formulas ----------
def test_formula_valida_entre_metricas_de_dos_entidades(modelo):
    modelo["metricas"].append({"id": "margen", "nombre": "Margen", "expresion": {"operacion": "resta", "izquierda": "total_ventas", "derecha": "total_pagado"}})
    assert _errores(modelo) == []
    assert modelo_efectivo(parsear_modelo(modelo)).metrica("margen") is not None


def test_formula_anidada_referenciando_otra_formula(modelo):
    modelo["metricas"].append({"id": "margen", "nombre": "Margen", "expresion": {"operacion": "resta", "izquierda": "total_ventas", "derecha": "total_pagado"}})
    modelo["metricas"].append({"id": "margen_doble", "nombre": "Margen doble", "expresion": {"operacion": "multiplicacion", "izquierda": "margen", "derecha": 2.0}})
    assert _errores(modelo) == []


def test_formula_con_expresion_embebida():
    modelo = copy.deepcopy(MODELO_BASE)
    modelo["metricas"].append(
        {
            "id": "margen_ajustado",
            "nombre": "Margen ajustado",
            "expresion": {"operacion": "suma", "izquierda": {"operacion": "resta", "izquierda": "total_ventas", "derecha": "total_pagado"}, "derecha": 100.0},
        }
    )
    assert _errores(modelo) == []


def test_formula_referencia_inexistente(modelo):
    modelo["metricas"].append({"id": "margen", "nombre": "Margen", "expresion": {"operacion": "resta", "izquierda": "total_ventas", "derecha": "no_existe"}})
    assert _errores(modelo) == [validacion.MET_FORMULA]


def test_formula_no_puede_referenciar_un_cociente(modelo):
    modelo["metricas"].append({"id": "x", "nombre": "X", "expresion": {"operacion": "suma", "izquierda": "ticket_promedio", "derecha": 1.0}})
    assert _errores(modelo) == [validacion.MET_FORMULA]


def test_formula_con_ciclo_directo_e_indirecto():
    modelo = copy.deepcopy(MODELO_BASE)
    modelo["metricas"].append({"id": "a", "nombre": "A", "expresion": {"operacion": "suma", "izquierda": "a", "derecha": 1.0}})
    assert _errores(modelo) == [validacion.MET_FORMULA]

    modelo = copy.deepcopy(MODELO_BASE)
    modelo["metricas"].append({"id": "a", "nombre": "A", "expresion": {"operacion": "suma", "izquierda": "b", "derecha": 1.0}})
    modelo["metricas"].append({"id": "b", "nombre": "B", "expresion": {"operacion": "resta", "izquierda": "a", "derecha": 1.0}})
    assert validacion.MET_FORMULA in _errores(modelo)


def test_formula_confirmada_sobre_metrica_propuesta(modelo):
    modelo["metricas"].append({"id": "margen", "nombre": "Margen", "expresion": {"operacion": "resta", "izquierda": "total_ventas", "derecha": "total_pagado"}})
    _metrica(modelo, "total_pagado")["estado"] = "propuesta"
    assert _errores(modelo) == [validacion.MET_CAMPO_NO_EFECTIVO]


# ---------- Dimensiones de tiempo ----------
def test_dimension_de_tiempo_invalida(modelo):
    modelo["dimensiones_tiempo"][0]["campo"] = "ventas.nada"
    modelo["dimensiones_tiempo"][1]["campo"] = "pagos.monto"
    assert _errores(modelo) == [validacion.TIEMPO_CAMPO, validacion.TIEMPO_TIPO]


# ---------- Modelo efectivo ----------
def test_modelo_efectivo_filtra_por_estado_y_confianza(modelo):
    _campo(modelo, "ventas", "precio_unitario")["estado"] = "rechazada"
    _campo(modelo, "vendedores", "email").update({"estado": "propuesta", "confianza": 0.95})
    _campo(modelo, "vendedores", "fecha_ingreso").update({"estado": "propuesta", "confianza": 0.5})
    modelo["relaciones"][3].update({"estado": "propuesta", "confianza": 0.6})  # pagos_medio
    _metrica(modelo, "cuotas_promedio")["estado"] = "propuesta"
    # Metrica y dimension de tiempo propuestas/sin estado sobre un campo que no entra
    modelo["metricas"].append({"id": "sobre_rechazado", "nombre": "x", "expresion": {"agregacion": "suma", "campo": "ventas.precio_unitario"}, "estado": "propuesta"})
    modelo["dimensiones_tiempo"].append({"campo": "vendedores.fecha_ingreso"})

    parseado = parsear_modelo(modelo)
    assert validar_estructura(parseado) == []
    efectivo = modelo_efectivo(parseado)

    campos_ventas = [campo.id for campo in efectivo.entidad("ventas").campos]
    assert "precio_unitario" not in campos_ventas and "importe" in campos_ventas
    campos_vendedores = [campo.id for campo in efectivo.entidad("vendedores").campos]
    assert "email" in campos_vendedores and "fecha_ingreso" not in campos_vendedores
    assert [relacion.id for relacion in efectivo.relaciones] == ["ventas_vendedor", "ventas_producto", "pagos_venta"]
    ids_metricas = [metrica.id for metrica in efectivo.metricas]
    assert "cuotas_promedio" not in ids_metricas and "sobre_rechazado" not in ids_metricas
    assert "ticket_promedio" in ids_metricas
    assert [dimension.campo for dimension in efectivo.dimensiones_tiempo] == ["ventas.fecha", "pagos.fecha_pago"]
    # El modelo original no se toco
    assert len(parseado.entidad("ventas").campos) == 7


# ---------- Contra las fuentes ----------
def test_fuente_columna_y_tipo_contra_las_fuentes(modelo, esquemas_prueba):
    _entidad(modelo, "ventas")["fuente"] = "ventas_2025"
    _campo(modelo, "vendedores", "email")["columna_origen"] = "correo"
    _campo(modelo, "productos", "precio_lista")["tipo_dato"] = "entero"
    errores = validar_contra_fuentes(parsear_modelo(modelo), esquemas_prueba)
    assert _codigos(errores) == [validacion.FUENTE_INEXISTENTE, validacion.COLUMNA_INEXISTENTE, validacion.COLUMNA_TIPO]
    assert errores[0].ubicacion == "entidades.ventas.fuente"
    assert "Columnas: id_vendedor, nombre" in errores[1].mensaje


# ---------- Diff entre versiones ----------
def test_calcular_diff(modelo):
    anterior = parsear_modelo(modelo)
    modelo["metricas"] = [metrica for metrica in modelo["metricas"] if metrica["id"] != "cuotas_promedio"]
    modelo["metricas"].append({"id": "nueva", "nombre": "Nueva", "expresion": {"agregacion": "conteo", "campo": "pagos.id_pago"}})
    _entidad(modelo, "ventas")["nombre"] = "Ventas del local"
    modelo["dimensiones_tiempo"].pop()
    diff = calcular_diff(anterior, parsear_modelo(modelo))
    assert diff["metricas"] == {"agregados": ["nueva"], "quitados": ["cuotas_promedio"], "cambiados": []}
    assert diff["entidades"] == {"agregados": [], "quitados": [], "cambiados": ["ventas"]}
    assert diff["relaciones"] == {"agregados": [], "quitados": [], "cambiados": []}
    assert diff["dimensiones_tiempo"]["quitados"] == ["pagos.fecha_pago"]


def test_el_json_serializa_y_vuelve_igual(modelo):
    parseado = parsear_modelo(modelo)
    assert ModeloSemantico.model_validate(parseado.model_dump(mode="json")) == parseado
