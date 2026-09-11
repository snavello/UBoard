"""API del dashboard con los 5 CSV, el modelo y el spec cargados de verdad:
KPIs, graficos, explorador, opciones y filtros que afectan a todo."""
import copy
import json

import pytest

CENTRO = {"María Pérez", "Juan Gómez", "Sofía Díaz", "Nicolás Álvarez"}


def _ruta(workspace_id: int, sufijo: str = "") -> str:
    return f"/api/workspaces/{workspace_id}/dashboard{sufijo}"


def _filtros(**activos) -> str:
    return json.dumps(activos)


@pytest.fixture
def dashboard(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, spec_prueba) -> int:
    """Constructor de Acme logueado, con fuentes, modelo y spec cargados.
    Devuelve el id del workspace."""
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201
    respuesta = cliente.put(_ruta(workspace_id), json=spec_prueba)
    assert respuesta.status_code == 201, respuesta.text
    return workspace_id


def test_spec_cargado_y_versiones(cliente, dashboard, spec_prueba):
    actual = cliente.get(_ruta(dashboard)).json()
    assert actual["numero"] == 1 and actual["modelo_version"] == 1
    assert actual["advertencias"] == []
    assert actual["contenido"]["titulo"] == "Ventas del almacén"
    assert actual["resumen"] == "5 filtros, 5 KPIs, 4 gráficos, 4 pestañas"

    otro = copy.deepcopy(spec_prueba)
    otro["graficos"] = otro["graficos"][:2]
    assert cliente.put(_ruta(dashboard), json=otro).json()["numero"] == 2
    assert [v["numero"] for v in cliente.get(_ruta(dashboard, "/versiones")).json()] == [2, 1]
    assert len(cliente.get(_ruta(dashboard, "/versiones/1")).json()["contenido"]["graficos"]) == 4
    assert cliente.get(_ruta(dashboard, "/versiones/7")).json()["codigo"] == "E-SPEC-03"


def test_kpis_y_graficos_cierran_entre_si(cliente, dashboard):
    kpis = {kpi["id"]: kpi for kpi in cliente.get(_ruta(dashboard, "/kpis")).json()}
    assert list(kpis) == ["k_total", "k_cantidad", "k_ticket", "k_unidades", "k_pagado"]
    assert kpis["k_cantidad"]["valor"] == 3000
    assert kpis["k_total"]["formato"] == "moneda" and kpis["k_total"]["titulo"] == "Total ventas"
    assert abs(kpis["k_ticket"]["valor"] - kpis["k_total"]["valor"] / 3000) < 0.01

    mes = cliente.get(_ruta(dashboard, "/graficos/g_mes")).json()
    assert mes["tipo"] == "linea" and mes["titulo"] == "Ventas por mes"
    assert mes["dimension"] == {"nombre": "ventas.fecha", "tipo": "fecha", "clase": "dimension", "granularidad": "mes"}
    assert mes["metrica"] == {"id": "total_ventas", "nombre": "Total ventas", "formato": "moneda"}
    assert 12 <= len(mes["filas"]) <= 13
    assert all(fila[0].endswith("-01") for fila in mes["filas"])
    assert abs(sum(fila[1] for fila in mes["filas"]) - kpis["k_total"]["valor"]) < 0.01

    vendedores = cliente.get(_ruta(dashboard, "/graficos/g_vendedores")).json()
    assert len(vendedores["filas"]) == 10
    valores = [fila[1] for fila in vendedores["filas"]]
    assert valores == sorted(valores, reverse=True)

    categorias = cliente.get(_ruta(dashboard, "/graficos/g_categorias")).json()
    assert abs(sum(fila[1] for fila in categorias["filas"]) - kpis["k_total"]["valor"]) < 0.01
    assert None in [fila[0] for fila in categorias["filas"]]  # productos huerfanos

    medios = cliente.get(_ruta(dashboard, "/graficos/g_medios")).json()
    assert medios["tipo"] == "torta" and len(medios["filas"]) == 6
    assert abs(sum(fila[1] for fila in medios["filas"]) - kpis["k_pagado"]["valor"]) < 0.01


def test_los_filtros_afectan_a_todo(cliente, dashboard):
    sin_filtro = {kpi["id"]: kpi["valor"] for kpi in cliente.get(_ruta(dashboard, "/kpis")).json()}
    activos = _filtros(f_sucursal=["Centro"], f_fecha=["2026-01-01", "2026-06-30"])

    kpis = {kpi["id"]: kpi["valor"] for kpi in cliente.get(_ruta(dashboard, "/kpis"), params={"filtros": activos}).json()}
    assert 0 < kpis["k_cantidad"] < sin_filtro["k_cantidad"]
    assert kpis["k_pagado"] < sin_filtro["k_pagado"]  # pagos filtrados por la sucursal de la venta

    vendedores = cliente.get(_ruta(dashboard, "/graficos/g_vendedores"), params={"filtros": activos}).json()
    assert {fila[0] for fila in vendedores["filas"]} <= CENTRO

    mes = cliente.get(_ruta(dashboard, "/graficos/g_mes"), params={"filtros": activos}).json()
    assert [fila[0] for fila in mes["filas"]] == [f"2026-0{m}-01" for m in range(1, 7)]
    assert abs(sum(fila[1] for fila in mes["filas"]) - kpis["k_total"]) < 0.01

    # Filtro por medio de pago: entidad del lado "muchos" respecto de ventas -> semi-join
    efectivo = {kpi["id"]: kpi["valor"] for kpi in cliente.get(_ruta(dashboard, "/kpis"), params={"filtros": _filtros(f_medio=["Efectivo"])}).json()}
    assert 0 < efectivo["k_cantidad"] < sin_filtro["k_cantidad"]

    explorador = cliente.get(_ruta(dashboard, "/explorador/ventas"), params={"filtros": activos}).json()
    assert explorador["total"] == kpis["k_cantidad"]


def test_opciones_de_filtros(cliente, dashboard):
    sucursal = cliente.get(_ruta(dashboard, "/filtros/f_sucursal/opciones")).json()
    assert sucursal == {"filtro": "f_sucursal", "tipo": "lista", "valores": ["Centro", "Norte", "Oeste"], "minimo": None, "maximo": None}
    medios = cliente.get(_ruta(dashboard, "/filtros/f_medio/opciones")).json()
    assert len(medios["valores"]) == 6
    fecha = cliente.get(_ruta(dashboard, "/filtros/f_fecha/opciones")).json()
    assert fecha["tipo"] == "rango_fecha"
    assert fecha["minimo"].startswith("2025-09") and fecha["maximo"].startswith("2026-08")
    assert cliente.get(_ruta(dashboard, "/filtros/f_nada/opciones")).json()["codigo"] == "E-SPEC-04"


def test_explorador_paginado_y_ordenado(cliente, dashboard):
    pagina_1 = cliente.get(_ruta(dashboard, "/explorador/productos")).json()
    assert pagina_1["titulo"] == "Productos"
    assert (pagina_1["pagina"], pagina_1["tamanio"], pagina_1["total"]) == (1, 25, 40)
    assert len(pagina_1["filas"]) == 25
    assert [(c["alias"], c["clase"], c["oculta"]) for c in pagina_1["columnas"]] == [
        ("__pk_id_producto", "dimension", True),
        ("nombre", "dimension", False),
        ("categoria", "dimension", False),
        ("precio_lista", "dimension", False),
        ("activo", "dimension", False),
        ("total_ventas", "metrica", False),
        ("unidades_vendidas", "metrica", False),
    ]
    assert pagina_1["columnas"][1]["titulo"] == "Producto"
    assert pagina_1["columnas"][5]["formato"] == "moneda"

    pagina_2 = cliente.get(_ruta(dashboard, "/explorador/productos"), params={"pagina": 2}).json()
    assert len(pagina_2["filas"]) == 15
    assert {fila[0] for fila in pagina_1["filas"]}.isdisjoint({fila[0] for fila in pagina_2["filas"]})

    ordenado = cliente.get(_ruta(dashboard, "/explorador/productos"), params={"orden": "total_ventas", "direccion": "desc", "tamanio": 5}).json()
    totales = [fila[5] for fila in ordenado["filas"]]
    assert totales == sorted(totales, reverse=True) and len(totales) == 5

    ventas = cliente.get(_ruta(dashboard, "/explorador/ventas")).json()
    assert (ventas["tamanio"], ventas["total"], len(ventas["filas"])) == (50, 3000, 50)
    assert [c["alias"] for c in ventas["columnas"]] == ["__pk_id_venta", "fecha", "importe", "cantidad", "vendedores.nombre", "productos.nombre"]
    assert ventas["columnas"][4]["titulo"] == "Nombre"

    assert cliente.get(_ruta(dashboard, "/explorador/productos"), params={"orden": "marca"}).json()["codigo"] == "E-CONS-08"
    assert cliente.get(_ruta(dashboard, "/explorador/sucursales")).json()["codigo"] == "E-SPEC-04"


def test_errores_de_paneles_y_filtros(cliente, dashboard):
    assert cliente.get(_ruta(dashboard, "/graficos/g_nada")).json()["codigo"] == "E-SPEC-04"
    roto = cliente.get(_ruta(dashboard, "/kpis"), params={"filtros": "{no json"})
    assert roto.status_code == 400 and roto.json()["codigo"] == "E-CONS-06"
    desconocido = cliente.get(_ruta(dashboard, "/kpis"), params={"filtros": _filtros(f_nada=["x"])})
    assert desconocido.status_code == 404 and desconocido.json()["codigo"] == "E-SPEC-04"


def test_spec_invalido_sin_modelo_y_sin_spec(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, spec_prueba):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    assert cliente.get(_ruta(workspace_id)).json()["codigo"] == "E-SPEC-02"
    assert cliente.get(_ruta(workspace_id, "/kpis")).json()["codigo"] == "E-SPEC-02"
    # Sin modelo, el spec no se puede validar
    assert cliente.put(_ruta(workspace_id), json=spec_prueba).json()["codigo"] == "E-MOD-02"

    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201
    roto = copy.deepcopy(spec_prueba)
    roto["graficos"][3]["metrica"] = "total_ventas"
    respuesta = cliente.put(_ruta(workspace_id), json=roto)
    assert respuesta.status_code == 422
    assert respuesta.json()["codigo"] == "E-SPEC-01"
    assert respuesta.json()["errores"][0]["codigo"] == "SPEC-CONSULTA"

    validacion = cliente.post(_ruta(workspace_id, "/validar"), json=roto).json()
    assert validacion["valido"] is False
    assert cliente.post(_ruta(workspace_id, "/validar"), json=spec_prueba).json()["valido"] is True
    assert cliente.get(_ruta(workspace_id)).json()["codigo"] == "E-SPEC-02"  # nada se guardo


def test_si_el_modelo_cambia_el_dashboard_avisa(cliente, dashboard, modelo_prueba):
    recortado = copy.deepcopy(modelo_prueba)
    recortado["metricas"] = [m for m in recortado["metricas"] if m["id"] != "total_pagado"]
    assert cliente.put(f"/api/workspaces/{dashboard}/modelo", json=recortado).json()["numero"] == 2
    actual = cliente.get(_ruta(dashboard)).json()
    assert actual["modelo_version"] == 1
    codigos = {advertencia["codigo"] for advertencia in actual["advertencias"]}
    assert codigos == {"SPEC-KPI-METRICA", "SPEC-GRAFICO-METRICA"}
    # Los paneles que dependen de la metrica que ya no existe fallan con codigo claro
    assert cliente.get(_ruta(dashboard, "/graficos/g_medios")).json()["codigo"] == "E-CONS-01"


def test_roles_y_aislamiento(cliente, dashboard, datos, ingresar, spec_prueba):
    cliente.post("/api/auth/logout")
    assert cliente.get(_ruta(dashboard, "/kpis")).status_code == 401

    ingresar("visualizador@acme.test")
    assert cliente.get(_ruta(dashboard)).status_code == 200
    assert cliente.get(_ruta(dashboard, "/kpis")).status_code == 200
    assert cliente.get(_ruta(dashboard, "/explorador/productos")).status_code == 200
    assert cliente.put(_ruta(dashboard), json=spec_prueba).status_code == 403
    assert cliente.post(_ruta(dashboard, "/validar"), json=spec_prueba).status_code == 403
    cliente.post("/api/auth/logout")

    ingresar("constructor@beta.test")
    ajeno = cliente.get(_ruta(dashboard, "/kpis"))
    assert ajeno.status_code == 404 and ajeno.json()["codigo"] == "E-WS-01"


def _proponer_spec(cliente, cola, workspace_id: int) -> dict:
    respuesta = cliente.post(_ruta(workspace_id, "/proponer"))
    assert respuesta.status_code == 202, respuesta.text
    tarea = respuesta.json()
    assert tarea["tipo"] == "inferencia.proponer_spec"
    cola.esperar(tarea["id"], timeout=120)
    return cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea['id']}").json()


def test_proponer_spec_sin_respuesta_de_claude_guarda_el_base(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, cola):
    """El conftest instala un cliente falso sin respuestas en todos los tests
    (nunca red): Claude falla con E-INF-01 y la propuesta sigue solo con el
    generador determinista, igual que si no hubiera clave configurada."""
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201

    tarea = _proponer_spec(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    resultado = tarea["resultado"]
    assert resultado["version"] == 1
    assert resultado["claude"]["usado"] is False
    assert resultado["claude"]["advertencia"].startswith("E-INF-01")

    actual = cliente.get(_ruta(workspace_id)).json()
    assert actual["numero"] == 1 and actual["operacion"] == "proponer_spec" and actual["modelo_version"] == 1
    spec = actual["contenido"]
    assert len(spec["kpis"]) == 8
    assert len(spec["graficos"]) == 4  # 1 linea + 3 barras, igual que el generador puro
    assert len(spec["explorador"]["pestanias"]) == 5
    kpis_reales = cliente.get(_ruta(workspace_id, "/kpis")).json()
    assert len(kpis_reales) == 8 and kpis_reales[0]["valor"] is not None


def test_proponer_spec_con_claude_falso_cura_y_cachea(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, cola, llm_falso, sesion_db):
    from app.catalogo.tablas import Inferencia
    from app.dashboard.generador import generar_spec_base
    from app.modelo.esquema import ModeloSemantico
    from app.modelo.validacion import modelo_efectivo

    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201

    base = generar_spec_base(modelo_efectivo(ModeloSemantico.model_validate(modelo_prueba)))
    curacion = {
        "titulo": "Panel de Almacén Don José",
        "filtros": [{"id": f.id, "etiqueta": f.id} for f in base.filtros],
        "kpis": [{"id": k.id, "titulo": k.id} for k in reversed(base.kpis)],
        "graficos": [{"id": g.id, "titulo": g.id, "incluir": True} for g in base.graficos],
        "pestanias": [{"entidad": p.entidad, "titulo": p.entidad} for p in base.explorador.pestanias],
    }
    falso = llm_falso([curacion])
    tarea = _proponer_spec(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada", tarea
    claude = tarea["resultado"]["claude"]
    assert claude == {"usado": True, "cache": False, "modelo": "claude-falso", "tokens_entrada": 100, "tokens_salida": 50}
    assert len(falso.pedidos) == 1 and "pestanias" in falso.pedidos[0]["usuario"]

    actual = cliente.get(_ruta(workspace_id)).json()
    assert actual["contenido"]["titulo"] == "Panel de Almacén Don José"
    assert [k["metrica"] for k in actual["contenido"]["kpis"]] == [k.metrica for k in reversed(base.kpis)]
    guardadas = sesion_db.query(Inferencia).filter_by(workspace_id=workspace_id, tipo="spec").all()
    assert len(guardadas) == 1

    # Reproponer con el mismo modelo: mismo pedido, sale de la cache
    falso = llm_falso([])
    tarea = _proponer_spec(cliente, cola, workspace_id)
    assert tarea["estado"] == "terminada" and tarea["resultado"]["claude"]["cache"] is True
    assert falso.pedidos == []
    assert cliente.get(_ruta(workspace_id)).json()["numero"] == 2


def test_proponer_spec_sin_modelo_cargado(cliente, datos, ingresar, cola):
    ingresar("constructor@acme.test")
    tarea = _proponer_spec(cliente, cola, datos.acme_workspace_id)
    assert tarea["estado"] == "error"
    assert tarea["error"].startswith("E-MOD-02")


def test_proponer_spec_exige_constructor(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, cola):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba)
    ingresar("visualizador@acme.test")
    assert cliente.post(_ruta(workspace_id, "/proponer")).status_code == 403
    ingresar("constructor@beta.test")
    assert cliente.post(_ruta(workspace_id, "/proponer")).status_code == 404


def test_operaciones_granulares_crean_versiones(cliente, dashboard, spec_prueba):
    ruta = _ruta(dashboard, "/operaciones")
    assert "crear_grafico" in cliente.get(ruta).json()

    respuesta = cliente.post(ruta, json={"operacion": "editar_titulo", "titulo": "Panel de ventas"})
    assert respuesta.status_code == 201, respuesta.text
    version = respuesta.json()
    assert version["numero"] == 2 and version["operacion"] == "editar_titulo"
    assert version["contenido"]["titulo"] == "Panel de ventas"
    assert version["resumen"] == "Título del dashboard: 'Panel de ventas'"

    # Operacion desconocida y parametros invalidos: E-SPEC-07, sin version nueva
    respuesta = cliente.post(ruta, json={"operacion": "hacer_magia"})
    assert respuesta.status_code == 400 and respuesta.json()["codigo"] == "E-SPEC-07"
    respuesta = cliente.post(ruta, json={"operacion": "eliminar_kpi"})
    assert respuesta.status_code == 400 and respuesta.json()["codigo"] == "E-SPEC-07"
    # No aplicable: E-SPEC-08
    respuesta = cliente.post(ruta, json={"operacion": "eliminar_kpi", "kpi": "no_existe"})
    assert respuesta.status_code == 400 and respuesta.json()["codigo"] == "E-SPEC-08"
    # Aplicable pero el resultado no valida: E-SPEC-01 (dimension que multiplicaria filas)
    respuesta = cliente.post(
        ruta, json={"operacion": "crear_grafico", "tipo": "barras", "metrica": "total_ventas", "dimension": "medios_pago.nombre"}
    )
    assert respuesta.status_code == 422 and respuesta.json()["codigo"] == "E-SPEC-01"
    assert cliente.get(_ruta(dashboard)).json()["numero"] == 2, "ninguna de las fallidas creo version"

    respuesta = cliente.post(
        ruta, json={"operacion": "crear_grafico", "tipo": "barras", "metrica": "total_ventas", "dimension": "vendedores.sucursal", "titulo": "Por sucursal"}
    )
    assert respuesta.status_code == 201 and respuesta.json()["numero"] == 3
    graficos = cliente.get(_ruta(dashboard, "/kpis"))  # sanity: el dashboard sigue sirviendo bien
    assert graficos.status_code == 200
    grafico_nuevo = next(g for g in respuesta.json()["contenido"]["graficos"] if g["dimension"] == "vendedores.sucursal")
    assert cliente.get(_ruta(dashboard, f"/graficos/{grafico_nuevo['id']}")).status_code == 200

    versiones = cliente.get(_ruta(dashboard, "/versiones")).json()
    assert [v["operacion"] for v in versiones] == ["crear_grafico", "editar_titulo", "cargar_json"]


def test_operaciones_exigen_constructor(cliente, dashboard, datos, ingresar):
    ingresar("visualizador@acme.test")
    assert cliente.post(_ruta(dashboard, "/operaciones"), json={"operacion": "editar_titulo", "titulo": "x"}).status_code == 403
    ingresar("constructor@beta.test")
    assert cliente.post(_ruta(dashboard, "/operaciones"), json={"operacion": "editar_titulo", "titulo": "x"}).status_code == 404


def test_restaurar_version(cliente, dashboard, spec_prueba):
    ruta = _ruta(dashboard)
    otro = copy.deepcopy(spec_prueba)
    otro["graficos"] = otro["graficos"][:2]
    cliente.put(ruta, json=otro)  # version 2, con 2 graficos

    respuesta = cliente.post(f"{ruta}/versiones/1/restaurar")
    assert respuesta.status_code == 201, respuesta.text
    version_3 = respuesta.json()
    assert version_3["numero"] == 3 and version_3["operacion"] == "restaurar"
    assert version_3["resumen"] == "Se restauró la versión 1"
    assert len(version_3["contenido"]["graficos"]) == 4
    assert version_3["diff"]["graficos"]["agregados"] == sorted({g["id"] for g in spec_prueba["graficos"]} - {g["id"] for g in otro["graficos"]})
    assert cliente.get(ruta).json()["numero"] == 3

    inexistente = cliente.post(f"{ruta}/versiones/99/restaurar")
    assert inexistente.status_code == 404 and inexistente.json()["codigo"] == "E-SPEC-03"
