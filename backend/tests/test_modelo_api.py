"""API del modelo semantico: cargar, validar, leer, versiones, roles y
aislamiento. Con Postgres y los 5 CSV ingestados de verdad."""
import copy


def _ruta(workspace_id: int) -> str:
    return f"/api/workspaces/{workspace_id}/modelo"


def test_sin_modelo_cargado(cliente, datos, ingresar):
    ingresar("constructor@acme.test")
    respuesta = cliente.get(_ruta(datos.acme_workspace_id))
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "E-MOD-02"
    assert cliente.get(f"{_ruta(datos.acme_workspace_id)}/versiones").json() == []


def test_cargar_leer_y_versionar(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)

    respuesta = cliente.put(_ruta(workspace_id), json=modelo_prueba)
    assert respuesta.status_code == 201, respuesta.text
    version_1 = respuesta.json()
    assert version_1["numero"] == 1
    assert version_1["operacion"] == "cargar_json"
    assert version_1["diff"] is None
    assert version_1["resumen"] == "5 entidades, 4 relaciones, 8 métricas, 2 dimensiones de tiempo"
    assert version_1["autor_id"] == datos.acme_constructor.id
    assert version_1["contenido"]["version"] == 1
    assert [entidad["id"] for entidad in version_1["contenido"]["entidades"]] == ["ventas", "vendedores", "productos", "pagos", "medios_pago"]

    actual = cliente.get(_ruta(workspace_id)).json()
    assert actual["numero"] == 1
    assert actual["contenido"] == version_1["contenido"]
    efectivo = cliente.get(f"{_ruta(workspace_id)}?efectivo=true").json()
    assert efectivo["contenido"] == version_1["contenido"]  # todo confirmado

    # Segunda version: sacamos una metrica; el diff lo registra
    cambiado = copy.deepcopy(modelo_prueba)
    cambiado["metricas"] = [metrica for metrica in cambiado["metricas"] if metrica["id"] != "cuotas_promedio"]
    respuesta = cliente.put(_ruta(workspace_id), json=cambiado)
    assert respuesta.status_code == 201, respuesta.text
    version_2 = respuesta.json()
    assert version_2["numero"] == 2
    assert version_2["contenido"]["version"] == 2
    assert version_2["diff"]["metricas"]["quitados"] == ["cuotas_promedio"]

    versiones = cliente.get(f"{_ruta(workspace_id)}/versiones").json()
    assert [version["numero"] for version in versiones] == [2, 1]
    assert "contenido" not in versiones[0]
    vieja = cliente.get(f"{_ruta(workspace_id)}/versiones/1").json()
    assert any(metrica["id"] == "cuotas_promedio" for metrica in vieja["contenido"]["metricas"])
    inexistente = cliente.get(f"{_ruta(workspace_id)}/versiones/9")
    assert inexistente.status_code == 404
    assert inexistente.json()["codigo"] == "E-MOD-03"


def test_un_modelo_invalido_no_crea_version(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(_ruta(workspace_id), json=modelo_prueba).status_code == 201

    roto = copy.deepcopy(modelo_prueba)
    roto["entidades"][0]["campos"][1]["columna_origen"] = "fecha_venta"
    respuesta = cliente.put(_ruta(workspace_id), json=roto)
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["codigo"] == "E-MOD-01"
    assert cuerpo["errores"][0]["codigo"] == "MOD-COLUMNA-INEXISTENTE"
    assert cuerpo["errores"][0]["ubicacion"] == "entidades.ventas.campos.fecha"

    mal_json = copy.deepcopy(modelo_prueba)
    mal_json["entidades"][0]["tipo"] = "tabla"
    respuesta = cliente.put(_ruta(workspace_id), json=mal_json)
    assert respuesta.status_code == 422
    assert respuesta.json()["errores"][0]["codigo"] == "MOD-JSON"

    assert [version["numero"] for version in cliente.get(f"{_ruta(workspace_id)}/versiones").json()] == [1]


def test_validar_sin_guardar(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)

    respuesta = cliente.post(f"{_ruta(workspace_id)}/validar", json=modelo_prueba)
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {"valido": True, "errores": [], "resumen": "5 entidades, 4 relaciones, 8 métricas, 2 dimensiones de tiempo"}

    roto = copy.deepcopy(modelo_prueba)
    roto["relaciones"][0]["hacia"]["campo"] = "nombre"
    resultado = cliente.post(f"{_ruta(workspace_id)}/validar", json=roto).json()
    assert resultado["valido"] is False
    assert {error["codigo"] for error in resultado["errores"]} == {"MOD-REL-NO-PK", "MOD-REL-TIPOS"}

    assert cliente.post(f"{_ruta(workspace_id)}/validar", json={"entidades": "no"}).json()["valido"] is False
    # Nada se guardo
    assert cliente.get(_ruta(workspace_id)).status_code == 404


def test_sin_fuentes_cargadas_el_modelo_no_pasa(cliente, datos, ingresar, modelo_prueba):
    ingresar("constructor@beta.test")
    respuesta = cliente.put(_ruta(datos.beta_workspace_id), json=modelo_prueba)
    assert respuesta.status_code == 422
    codigos = {error["codigo"] for error in respuesta.json()["errores"]}
    assert codigos == {"MOD-FUENTE-INEXISTENTE"}


def test_roles_y_aislamiento(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba):
    workspace_id = datos.acme_workspace_id
    assert cliente.get(_ruta(workspace_id)).status_code == 401

    ingresar("constructor@acme.test")
    cargar_datos_prueba(workspace_id)
    assert cliente.put(_ruta(workspace_id), json=modelo_prueba).status_code == 201
    cliente.post("/api/auth/logout")

    ingresar("visualizador@acme.test")
    assert cliente.get(_ruta(workspace_id)).status_code == 200
    assert cliente.get(f"{_ruta(workspace_id)}/versiones/1").status_code == 200
    assert cliente.put(_ruta(workspace_id), json=modelo_prueba).status_code == 403
    assert cliente.post(f"{_ruta(workspace_id)}/validar", json=modelo_prueba).status_code == 403
    cliente.post("/api/auth/logout")

    ingresar("constructor@beta.test")
    ajeno = cliente.get(_ruta(workspace_id))
    assert ajeno.status_code == 404
    assert ajeno.json()["codigo"] == "E-WS-01"
