"""Aislamiento entre organizaciones: un usuario solo ve los workspaces de la
suya; los ajenos no existen para el (404, no 403)."""


def test_anonimo_no_lista_workspaces(cliente):
    assert cliente.get("/api/workspaces").status_code == 401


def test_constructor_solo_ve_el_workspace_de_su_organizacion(cliente, datos, ingresar):
    ingresar("constructor@acme.test")
    respuesta = cliente.get("/api/workspaces")
    assert respuesta.status_code == 200
    workspaces = respuesta.json()
    assert len(workspaces) == 1
    assert workspaces[0]["id"] == datos.acme_workspace_id
    assert workspaces[0]["organizacion_id"] == datos.acme.id
    assert workspaces[0]["nombre"] == "Principal"

    propio = cliente.get(f"/api/workspaces/{datos.acme_workspace_id}")
    assert propio.status_code == 200

    ajeno = cliente.get(f"/api/workspaces/{datos.beta_workspace_id}")
    assert ajeno.status_code == 404
    assert ajeno.json()["codigo"] == "E-WS-01"

    inexistente = cliente.get("/api/workspaces/999999")
    assert inexistente.status_code == 404
    assert inexistente.json()["codigo"] == "E-WS-01"


def test_visualizador_lee_su_workspace(cliente, datos, ingresar):
    ingresar("visualizador@acme.test")
    assert cliente.get(f"/api/workspaces/{datos.acme_workspace_id}").status_code == 200
    assert cliente.get(f"/api/workspaces/{datos.beta_workspace_id}").status_code == 404


def test_plataforma_no_tiene_workspaces(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    assert cliente.get("/api/workspaces").json() == []
    assert cliente.get(f"/api/workspaces/{datos.acme_workspace_id}").status_code == 404
