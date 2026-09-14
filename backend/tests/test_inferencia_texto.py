"""Claude propone la estructura de un texto sin delimitador estandar (fase
4, "texto estructurado"), sin red: armado del pedido, reintento con
feedback, cache por huella (via la tabla `inferencia`, probado en
test_fuentes_api.py que ejercita la tarea completa)."""
import json

import pytest

from app.inferencia.llm import ClienteFalso
from app.inferencia.texto import armar_pedido, consultar_estructura, huella_pedido
from app.nucleo.errores import ErrorApp

LINEAS = ["2026-01-05 Ana Martinez $150000", "2026-01-06 Bruno Diaz $87500"]

RECETA_BUENA = {
    "modo": "regex",
    "patron": r"^(\d{4}-\d{2}-\d{2}) (.+?) \$(\d+)$",
    "columnas": [{"nombre": "fecha"}, {"nombre": "nombre"}, {"nombre": "importe"}],
}

# Grupos de mas: no coincide con la cantidad de columnas declaradas
RECETA_MALA = {
    "modo": "regex",
    "patron": r"^(\d{4}-\d{2}-\d{2}) (.+?) \$(\d+)(x?)$",
    "columnas": [{"nombre": "fecha"}, {"nombre": "nombre"}, {"nombre": "importe"}],
}


def test_armar_pedido_es_compacto_y_lleva_las_lineas_tal_cual():
    pedido = json.loads(armar_pedido(LINEAS))
    assert pedido == {"lineas": LINEAS}
    assert armar_pedido(LINEAS) == '{"lineas":["2026-01-05 Ana Martinez $150000","2026-01-06 Bruno Diaz $87500"]}'


def test_consultar_estructura_reintenta_una_vez_con_el_error_como_feedback():
    cliente = ClienteFalso([RECETA_MALA, RECETA_BUENA])
    pedido = armar_pedido(LINEAS)
    receta, cruda = consultar_estructura(cliente, LINEAS, pedido)
    assert receta.modo == "regex" and receta.patron == RECETA_BUENA["patron"]
    assert len(cliente.pedidos) == 2
    assert "grupo" in cliente.pedidos[1]["usuario"] and "corregilos" in cliente.pedidos[1]["usuario"]
    assert cruda.tokens_entrada == 100


def test_consultar_estructura_dos_fallos_da_e_inf_06():
    cliente = ClienteFalso([RECETA_MALA, RECETA_MALA])
    with pytest.raises(ErrorApp) as error:
        consultar_estructura(cliente, LINEAS, armar_pedido(LINEAS))
    assert error.value.codigo == "E-INF-06"


def test_huella_pedido_es_la_generica_de_inferencia():
    # No es un hash propio: reusa exactamente el de semantica.py/spec.py.
    from app.inferencia.semantica import huella_pedido as huella_generica

    pedido = armar_pedido(LINEAS)
    assert huella_pedido("claude-sonnet-5", "sistema", pedido) == huella_generica("claude-sonnet-5", "sistema", pedido)
