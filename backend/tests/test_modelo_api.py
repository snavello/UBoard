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


def _proponer(cliente, cola, workspace_id: int) -> dict:
    respuesta = cliente.post(f"{_ruta(workspace_id)}/proponer")
    assert respuesta.status_code == 202, respuesta.text
    tarea = respuesta.json()
    assert tarea["tipo"] == "inferencia.proponer_modelo"
    cola.esperar(tarea["id"], timeout=120)
    return cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea['id']}").json()


def test_proponer_modelo_desde_cero_y_reproponer_fusiona(cliente, datos, ingresar, cargar_datos_prueba, cola):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)

    tarea = _proponer(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    resultado = tarea["resultado"]
    assert resultado["version"] == 1
    assert resultado["resumen"].startswith("5 entidades, 4 relaciones")
    assert {(r["desde"], r["hacia"]) for r in resultado["relaciones"]} == {
        ("ventas.vendedor", "vendedores.id_vendedor"),
        ("ventas.id_producto", "productos.id_producto"),
        ("pagos.id_venta", "ventas.id_venta"),
        ("pagos.id_medio_pago", "medios_pago.id_medio_pago"),
    }
    assert all(r["confianza"] >= 0.9 and r["estado"] == "propuesta" for r in resultado["relaciones"])

    actual = cliente.get(_ruta(workspace_id)).json()
    assert actual["numero"] == 1 and actual["operacion"] == "proponer_modelo"
    assert actual["autor_id"] == datos.acme_constructor.id
    efectivo = cliente.get(f"{_ruta(workspace_id)}?efectivo=true").json()["contenido"]
    assert len(efectivo["relaciones"]) == 4 and efectivo["metricas"] == []

    # El constructor confirma una metrica a mano (cargando el JSON entero, como en la fase 1)
    contenido = actual["contenido"]
    metrica = next(m for m in contenido["metricas"] if m["id"] == "total_importe")
    metrica["estado"] = "confirmada"
    metrica["nombre"] = "Facturación"
    assert cliente.put(_ruta(workspace_id), json=contenido).status_code == 201

    # Reproponer: version 3, la metrica confirmada sigue con su nombre
    tarea = _proponer(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    assert tarea["resultado"]["version"] == 3
    version_3 = cliente.get(_ruta(workspace_id)).json()
    assert version_3["operacion"] == "proponer_modelo"
    facturacion = next(m for m in version_3["contenido"]["metricas"] if m["id"] == "total_importe")
    assert facturacion["estado"] == "confirmada" and facturacion["nombre"] == "Facturación"
    assert version_3["diff"]["metricas"]["cambiados"] == []


def _respuesta_claude(modelo: dict) -> dict:
    nombres = {"ventas": "Ventas", "vendedores": "Vendedores", "productos": "Productos", "pagos": "Pagos", "medios_pago": "Medios de pago"}
    entidades = [
        {
            "id": e["id"],
            "nombre": nombres[e["id"]],
            "tipo": e["tipo"],
            "sinonimos": ["facturación"] if e["id"] == "ventas" else [],
            "campos": [{"id": c["id"], "nombre": c["nombre"].capitalize(), "tipo_semantico": c["tipo_semantico"]} for c in e["campos"]],
        }
        for e in modelo["entidades"]
    ]
    metricas = [
        {"id": "total_ventas", "nombre": "Total ventas", "tipo": "agregacion", "agregacion": "suma", "campo": "ventas.importe", "formato": "moneda"},
        {"id": "cantidad_ventas", "nombre": "Cantidad de ventas", "tipo": "agregacion", "agregacion": "conteo", "campo": "ventas.id_venta", "formato": "entero"},
        {"id": "ticket_promedio", "nombre": "Ticket promedio", "tipo": "cociente", "numerador": "total_ventas", "denominador": "cantidad_ventas", "formato": "moneda"},
    ]
    return {"entidades": entidades, "metricas": metricas}


def test_proponer_con_claude_falso_aplica_semantica_y_cachea(cliente, datos, ingresar, cargar_datos_prueba, cola, llm_falso, sesion_db):
    from app.catalogo.tablas import Inferencia

    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)

    # Primero solo heuristica (el cliente falso sin respuestas falla como E-INF-01 y la tarea sigue)
    tarea = _proponer(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    assert tarea["resultado"]["claude"]["usado"] is False
    assert tarea["resultado"]["claude"]["advertencia"].startswith("E-INF-01")
    heuristico = cliente.get(_ruta(workspace_id)).json()["contenido"]
    assert heuristico["entidades"][0]["nombre"] == "Medios pago"

    # Ahora con respuesta grabada: nombres, sinonimos y metricas de Claude
    falso = llm_falso([_respuesta_claude(heuristico)])
    tarea = _proponer(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    claude = tarea["resultado"]["claude"]
    assert claude == {"usado": True, "cache": False, "modelo": "claude-falso", "tokens_entrada": 100, "tokens_salida": 50}
    assert len(falso.pedidos) == 1 and "muestra" in falso.pedidos[0]["usuario"]
    actual = cliente.get(_ruta(workspace_id)).json()
    assert actual["numero"] == 2
    modelo = actual["contenido"]
    medios = next(e for e in modelo["entidades"] if e["id"] == "medios_pago")
    assert medios["nombre"] == "Medios de pago" and medios["origen"] == "llm"
    assert next(e for e in modelo["entidades"] if e["id"] == "ventas")["sinonimos"] == ["facturación"]
    assert [m["id"] for m in modelo["metricas"]] == ["total_ventas", "cantidad_ventas", "ticket_promedio"]
    assert all(m["origen"] == "llm" and m["estado"] == "propuesta" for m in modelo["metricas"])
    assert len([r for r in modelo["relaciones"] if r["confianza"] >= 0.9]) == 4, "las relaciones no las toca Claude"
    guardadas = sesion_db.query(Inferencia).filter_by(workspace_id=workspace_id).all()
    assert len(guardadas) == 1 and guardadas[0].tokens_entrada == 100 and guardadas[0].tipo == "semantica"

    # Tercera vez, mismo pedido: sale de la cache, sin llamar al cliente
    falso = llm_falso([])
    tarea = _proponer(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    assert tarea["resultado"]["claude"]["cache"] is True and falso.pedidos == []
    assert cliente.get(_ruta(workspace_id)).json()["numero"] == 3


def test_proponer_sin_fuentes_deja_la_tarea_en_error(cliente, datos, ingresar, cola):
    ingresar("constructor@acme.test")
    tarea = _proponer(cliente, cola, datos.acme_workspace_id)
    assert tarea["estado"] == "error"
    assert tarea["error"].startswith("E-INF-02")


def test_proponer_exige_constructor(cliente, datos, ingresar, cola):
    ingresar("visualizador@acme.test")
    assert cliente.post(f"{_ruta(datos.acme_workspace_id)}/proponer").status_code == 403
    ingresar("constructor@beta.test")
    assert cliente.post(f"{_ruta(datos.acme_workspace_id)}/proponer").status_code == 404
