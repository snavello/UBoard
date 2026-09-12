"""API del asistente (pasos 19 y 21): un endpoint, dos catalogos segun el
rol, con un ClienteFalso (nunca red)."""
import json

import pytest


@pytest.fixture
def workspace_listo(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, spec_prueba) -> int:
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201
    assert cliente.put(f"/api/workspaces/{workspace_id}/dashboard", json=spec_prueba).status_code == 201
    return workspace_id


def _ruta(workspace_id: int) -> str:
    return f"/api/workspaces/{workspace_id}/asistente/mensajes"


def test_constructor_pide_un_cambio_y_se_aplica(cliente, workspace_listo, llm_falso):
    llm_falso(
        respuestas_chat=[
            [("crear_kpi", {"metrica": "cantidad_ventas", "titulo": "Cantidad"})],
            "Listo, creé el KPI 'Cantidad'.",
        ]
    )
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "agregá un KPI con la cantidad de ventas"})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["texto"] == "Listo, creé el KPI 'Cantidad'."
    assert len(cuerpo["acciones"]) == 1 and cuerpo["acciones"][0]["herramienta"] == "crear_kpi"

    actual = cliente.get(f"/api/workspaces/{workspace_listo}/dashboard").json()
    assert actual["numero"] == 2
    assert any(kpi["titulo"] == "Cantidad" for kpi in actual["contenido"]["kpis"])


def test_visualizador_solo_puede_consultar(cliente, workspace_listo, datos, ingresar, llm_falso):
    llm_falso(respuestas_chat=["Vendió $ 1.234.567 en marzo."])
    ingresar("visualizador@acme.test")
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "¿cuánto vendió en marzo?"})
    assert respuesta.status_code == 200
    assert respuesta.json()["texto"] == "Vendió $ 1.234.567 en marzo."

    # Si igual pidiera una herramienta de escritura, no existe en su catalogo:
    # el motor la reporta como error a Claude, nunca la ejecuta.
    llm_falso(respuestas_chat=[[("eliminar_kpi", {"kpi": "k_total"})], "No puedo hacer eso."])
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "borrá el kpi de total"})
    assert respuesta.status_code == 200 and respuesta.json()["acciones"] == []
    assert cliente.get(f"/api/workspaces/{workspace_listo}/dashboard").json()["numero"] == 1, "no se creo ninguna version"


def test_mensaje_vacio_es_400(cliente, workspace_listo):
    assert cliente.post(_ruta(workspace_listo), json={"mensaje": ""}).status_code == 422


def test_sin_modelo_cargado_es_e_mod_02(cliente, datos, ingresar):
    ingresar("constructor@beta.test")
    respuesta = cliente.post(_ruta(datos.beta_workspace_id), json={"mensaje": "hola"})
    assert respuesta.status_code == 404 and respuesta.json()["codigo"] == "E-MOD-02"


def test_organizacion_ajena_da_404(cliente, workspace_listo, datos, ingresar):
    ingresar("constructor@beta.test")
    assert cliente.post(_ruta(workspace_listo), json={"mensaje": "hola"}).status_code == 404


def test_sin_clave_de_claude_configurada_es_e_asi_04(cliente, workspace_listo, monkeypatch):
    import app.api.asistente as api_asistente

    monkeypatch.setattr(api_asistente, "obtener_cliente_llm", lambda: None)
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "hola"})
    assert respuesta.status_code == 400 and respuesta.json()["codigo"] == "E-ASI-04"


def test_limite_de_vueltas_es_502(cliente, workspace_listo, llm_falso):
    pedido_tool = [("confirmar_metrica", {"metrica": "total_ventas"})]
    llm_falso(respuestas_chat=[pedido_tool] * 4)
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "confirmá todo"})
    assert respuesta.status_code == 502 and respuesta.json()["codigo"] == "E-ASI-02"


# ---------- Filtros del Tablero (paso 21) ----------
def test_pregunta_del_visualizador_respeta_los_filtros_activos(cliente, workspace_listo, ingresar, llm_falso):
    ingresar("visualizador@acme.test")
    llm_falso(respuestas_chat=[[("consultar", {"metricas": ["cantidad_ventas"]})], "No encontré ventas de esa persona con los filtros activos."])
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "¿cuántas ventas tuvo?", "filtros": {"f_vendedor": ["nadie existe"]}})
    assert respuesta.status_code == 200, respuesta.text
    resultado = json.loads(respuesta.json()["acciones"][0]["resultado"])
    assert resultado["filas"] == [[0]], "el filtro de vendedor tiene que dejar la consulta en cero filas coincidentes"


def test_filtro_inexistente_es_e_spec_04(cliente, workspace_listo):
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "hola", "filtros": {"f_no_existe": ["x"]}})
    assert respuesta.status_code == 404 and respuesta.json()["codigo"] == "E-SPEC-04"


def test_sin_filtros_no_cambia_nada(cliente, workspace_listo, llm_falso):
    """Un pedido sin `filtros` (o con {}) se comporta exactamente como antes del paso 21."""
    llm_falso(respuestas_chat=[[("consultar", {"metricas": ["cantidad_ventas"]})], "Hubo 3000 ventas."])
    respuesta = cliente.post(_ruta(workspace_listo), json={"mensaje": "¿cuántas ventas hubo?", "filtros": {}})
    assert respuesta.status_code == 200
    resultado = json.loads(respuesta.json()["acciones"][0]["resultado"])
    assert resultado["filas"] == [[3000]]
