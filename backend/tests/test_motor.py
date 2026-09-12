"""Motor del asistente (paso 19): el loop de tool-use contra un ClienteFalso
(nunca red), sobre un workspace con modelo y dashboard reales."""
import pytest

from app.asistente import motor
from app.catalogo.tablas import Workspace
from app.nucleo.errores import ErrorApp


@pytest.fixture
def workspace_listo(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, spec_prueba, sesion_db) -> Workspace:
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201
    assert cliente.put(f"/api/workspaces/{workspace_id}/dashboard", json=spec_prueba).status_code == 201
    return sesion_db.get(Workspace, workspace_id)


def test_armar_contexto_incluye_modelo_y_dashboard(workspace_listo, sesion_db):
    import json

    contexto = json.loads(motor.armar_contexto(sesion_db, workspace_listo))
    ids_metricas = {metrica["id"] for metrica in contexto["modelo"]["metricas"]}
    assert "total_ventas" in ids_metricas
    assert contexto["dashboard"]["titulo"] == "Ventas del almacén"
    assert "filtros_activos" not in contexto


def test_armar_contexto_incluye_filtros_activos_si_los_hay(workspace_listo, sesion_db):
    import json

    contexto = json.loads(motor.armar_contexto(sesion_db, workspace_listo, filtros_activos={"f_vendedor": ["Pérez"]}))
    assert contexto["filtros_activos"] == {"f_vendedor": ["Pérez"]}


def test_respuesta_de_texto_sin_herramientas(workspace_listo, datos, sesion_db, almacen_temporal, llm_falso):
    cliente_falso = llm_falso(respuestas_chat=["Todavía no tenés nada que preguntar."])
    respuesta = motor.conversar(
        cliente_falso,
        usuario=datos.acme_constructor,
        sesion=sesion_db,
        workspace=workspace_listo,
        almacen=almacen_temporal,
        mensaje="hola",
        contexto="{}",
    )
    assert respuesta.texto == "Todavía no tenés nada que preguntar." and respuesta.acciones == []
    assert len(cliente_falso.turnos_chat) == 1


def test_una_herramienta_y_despues_respuesta_final(workspace_listo, datos, sesion_db, almacen_temporal, llm_falso):
    cliente_falso = llm_falso(
        respuestas_chat=[
            [("crear_kpi", {"metrica": "cantidad_ventas", "titulo": "Cantidad"})],
            "Listo, creé el KPI 'Cantidad'.",
        ]
    )
    respuesta = motor.conversar(
        cliente_falso,
        usuario=datos.acme_constructor,
        sesion=sesion_db,
        workspace=workspace_listo,
        almacen=almacen_temporal,
        mensaje="agregá un KPI con la cantidad de ventas",
        contexto=motor.armar_contexto(sesion_db, workspace_listo),
    )
    assert respuesta.texto == "Listo, creé el KPI 'Cantidad'."
    assert len(respuesta.acciones) == 1 and respuesta.acciones[0].herramienta == "crear_kpi"
    assert "versión 2 del dashboard" in respuesta.acciones[0].resultado
    # El segundo turno le manda a Claude el resultado de la herramienta, no un error
    segundo_turno = cliente_falso.turnos_chat[1]
    tool_result = segundo_turno[-1]["content"][0]
    assert tool_result["tool_use_id"] == "llamada_falsa_0" and "is_error" not in tool_result


def test_varias_herramientas_en_un_turno(workspace_listo, datos, sesion_db, almacen_temporal, llm_falso):
    cliente_falso = llm_falso(
        respuestas_chat=[
            [
                ("crear_kpi", {"metrica": "cantidad_ventas", "titulo": "Cantidad"}),
                ("crear_kpi", {"metrica": "total_pagado", "titulo": "Pagado"}),
            ],
            "Listo, creé los dos KPIs.",
        ]
    )
    respuesta = motor.conversar(
        cliente_falso,
        usuario=datos.acme_constructor,
        sesion=sesion_db,
        workspace=workspace_listo,
        almacen=almacen_temporal,
        mensaje="agregá dos KPIs",
        contexto=motor.armar_contexto(sesion_db, workspace_listo),
    )
    assert len(respuesta.acciones) == 2
    segundo_turno = cliente_falso.turnos_chat[1]
    assert len(segundo_turno[-1]["content"]) == 2


def test_error_de_una_herramienta_se_reporta_como_tool_result_y_sigue(workspace_listo, datos, sesion_db, almacen_temporal, llm_falso):
    cliente_falso = llm_falso(
        respuestas_chat=[
            [("eliminar_metrica", {"metrica": "no_existe"})],
            "Esa métrica no existe, ¿me decís cuál es?",
        ]
    )
    respuesta = motor.conversar(
        cliente_falso,
        usuario=datos.acme_constructor,
        sesion=sesion_db,
        workspace=workspace_listo,
        almacen=almacen_temporal,
        mensaje="borrá la métrica no_existe",
        contexto=motor.armar_contexto(sesion_db, workspace_listo),
    )
    assert respuesta.texto == "Esa métrica no existe, ¿me decís cuál es?"
    assert respuesta.acciones == [], "una herramienta que fallo no cuenta como accion aplicada"
    segundo_turno = cliente_falso.turnos_chat[1]
    tool_result = segundo_turno[-1]["content"][0]
    assert tool_result["is_error"] is True and "E-MOD-05" in tool_result["content"]


def test_tope_de_vueltas(workspace_listo, datos, sesion_db, almacen_temporal, llm_falso):
    pedido_tool = [("confirmar_metrica", {"metrica": "total_ventas"})]
    cliente_falso = llm_falso(respuestas_chat=[pedido_tool, pedido_tool, pedido_tool, pedido_tool, pedido_tool])
    with pytest.raises(ErrorApp) as error:
        motor.conversar(
            cliente_falso,
            usuario=datos.acme_constructor,
            sesion=sesion_db,
            workspace=workspace_listo,
            almacen=almacen_temporal,
            mensaje="confirmá total_ventas",
            contexto=motor.armar_contexto(sesion_db, workspace_listo),
        )
    assert error.value.codigo == "E-ASI-02"
    assert len(cliente_falso.turnos_chat) == motor.MAX_VUELTAS


def test_visualizador_no_tiene_herramientas_de_escritura(workspace_listo, datos, sesion_db, almacen_temporal, llm_falso):
    cliente_falso = llm_falso(
        respuestas_chat=[
            [("crear_kpi", {"metrica": "cantidad_ventas", "titulo": "Cantidad"})],
            "No puedo hacer eso.",
        ]
    )
    respuesta = motor.conversar(
        cliente_falso,
        usuario=datos.acme_visualizador,
        sesion=sesion_db,
        workspace=workspace_listo,
        almacen=almacen_temporal,
        mensaje="agregá un KPI",
        contexto="{}",
    )
    assert respuesta.acciones == []
    tool_result = cliente_falso.turnos_chat[1][-1]["content"][0]
    assert tool_result["is_error"] is True and "E-ASI-03" in tool_result["content"]
