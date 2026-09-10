"""Curacion del spec con Claude (paso 14), sin red: armado del pedido,
validacion de la respuesta, reintento con feedback, aplicacion sobre el
spec base."""
import json
from pathlib import Path

import pytest

from app.dashboard.generador import generar_spec_base
from app.dashboard.validacion import validar_spec
from app.inferencia.llm import ClienteFalso
from app.inferencia.spec import SpecCurado, aplicar_curacion, armar_pedido, consultar_curacion, validar_curacion
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo
from app.nucleo.errores import ErrorApp

DATOS_PRUEBA = Path(__file__).resolve().parents[1].parent / "datos_prueba"


@pytest.fixture(scope="module")
def modelo() -> ModeloSemantico:
    contenido = json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))
    return modelo_efectivo(ModeloSemantico.model_validate(contenido))


@pytest.fixture
def base(modelo):
    return generar_spec_base(modelo)


def curacion_valida(spec) -> dict:
    return {
        "titulo": "Panel de ventas",
        "filtros": [{"id": f.id, "etiqueta": f"Filtro {f.id}"} for f in spec.filtros],
        "kpis": [{"id": k.id, "titulo": f"KPI {k.id}"} for k in reversed(spec.kpis)],  # protagonista distinto
        "graficos": [{"id": g.id, "titulo": f"Gráfico {g.id}", "incluir": g.tipo != "barras"} for g in spec.graficos],
        "pestanias": [{"entidad": p.entidad, "titulo": p.entidad.capitalize()} for p in spec.explorador.pestanias],
    }


def test_el_pedido_usa_nombres_del_modelo_no_ids_crudos(modelo, base):
    pedido = json.loads(armar_pedido(base, modelo))
    assert pedido["kpis"][0]["metrica"] == modelo.metrica(base.kpis[0].metrica).nombre
    grafico_linea = next(g for g in pedido["graficos"] if g["tipo"] == "linea")
    assert grafico_linea["dimension"] == "Fecha"
    assert {p["nombre"] for p in pedido["pestanias"]} == {e.nombre for e in modelo.entidades}


def test_validar_curacion_exige_todos_los_ids_salvo_incluir_false_en_graficos(modelo, base):
    assert validar_curacion(base, SpecCurado.model_validate(curacion_valida(base))) == []

    incompleta = curacion_valida(base)
    incompleta["kpis"] = incompleta["kpis"][1:]  # falta uno
    errores = validar_curacion(base, SpecCurado.model_validate(incompleta))
    assert any("faltan KPIs" in error for error in errores)

    inventada = curacion_valida(base)
    inventada["filtros"][0]["id"] = "f_inventado"
    errores = validar_curacion(base, SpecCurado.model_validate(inventada))
    assert any("no existen" in error for error in errores) and any("faltan filtros" in error for error in errores)


def test_consultar_curacion_reintenta_con_feedback_y_falla_a_la_segunda(modelo, base):
    buena = curacion_valida(base)
    mala = json.loads(json.dumps(buena))
    mala["pestanias"] = mala["pestanias"][:-1]  # falta una pestaña
    cliente = ClienteFalso([mala, buena])
    curado, cruda = consultar_curacion(cliente, base, armar_pedido(base, modelo))
    assert curado.titulo == "Panel de ventas"
    assert len(cliente.pedidos) == 2 and "faltan pestañas" in cliente.pedidos[1]["usuario"]
    assert cruda.tokens_entrada == 100

    cliente = ClienteFalso([mala, mala])
    with pytest.raises(ErrorApp) as error:
        consultar_curacion(cliente, base, armar_pedido(base, modelo))
    assert error.value.codigo == "E-SPEC-06"


def test_aplicar_curacion_reordena_titula_y_descarta_graficos(modelo, base):
    curado = SpecCurado.model_validate(curacion_valida(base))
    curado_spec = aplicar_curacion(base, curado)

    assert validar_spec(curado_spec, modelo) == []
    assert curado_spec.titulo == "Panel de ventas"
    assert [kpi.id for kpi in curado_spec.kpis] == [kpi.id for kpi in reversed(base.kpis)]
    assert curado_spec.kpis[0].titulo == f"KPI {base.kpis[-1].id}"
    assert all(g.tipo != "barras" for g in curado_spec.graficos), "se descartaron las barras"
    assert len(curado_spec.graficos) == len(base.graficos) - sum(1 for g in base.graficos if g.tipo == "barras")
    assert {p.entidad: p.titulo for p in curado_spec.explorador.pestanias} == {p.entidad: p.entidad.capitalize() for p in base.explorador.pestanias}
    # El spec base no se modifica
    assert base.titulo is None and [kpi.id for kpi in base.kpis][0] != curado_spec.kpis[0].id
