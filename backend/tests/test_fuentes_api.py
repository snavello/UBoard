"""API de fuentes: subida en segundo plano, polling, listado, muestra, resubida,
borrado, roles y aislamiento. Con Postgres, cola local y almacen temporal."""
import io

from openpyxl import Workbook

from app.nucleo.config import obtener_configuracion

CSV_VENTAS = b"IdVenta,Fecha,Importe\n1,2026-01-05,10.5\n2,06/01/2026,20\n"


def _subir(cliente, workspace_id: int, nombre: str, contenido: bytes):
    return cliente.post(f"/api/workspaces/{workspace_id}/fuentes", files=[("archivos", (nombre, contenido, "application/octet-stream"))])


def _procesar(cliente, cola, workspace_id: int, nombre: str, contenido: bytes) -> dict:
    respuesta = _subir(cliente, workspace_id, nombre, contenido)
    assert respuesta.status_code == 202, respuesta.text
    tareas = respuesta.json()
    assert len(tareas) == 1
    cola.esperar(tareas[0]["id"], timeout=60)
    tarea = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tareas[0]['id']}").json()
    assert tarea["estado"] == "terminada", tarea
    return tarea


def test_subir_procesar_listar_y_previsualizar(cliente, datos, cola, almacen_temporal, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    tarea = _procesar(cliente, cola, workspace_id, "Ventas 2026.csv", CSV_VENTAS)
    assert tarea["tipo"] == "ingesta.procesar_archivo"
    assert tarea["resultado"]["fuentes"][0]["nombre_tabla"] == "ventas_2026"
    assert tarea["resultado"]["fuentes"][0]["filas"] == 2
    assert tarea["resultado"]["fuentes"][0]["reemplazada"] is False

    fuentes = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()
    assert len(fuentes) == 1
    fuente = fuentes[0]
    assert fuente["nombre_tabla"] == "ventas_2026"
    assert fuente["archivo_origen"] == "Ventas 2026.csv"
    assert fuente["estado"] == "lista"
    assert fuente["filas"] == 2
    assert len(fuente["huella"]) == 16
    assert [(columna["nombre"], columna["tipo"]) for columna in fuente["columnas"]] == [
        ("id_venta", "entero"),
        ("fecha", "fecha"),
        ("importe", "decimal"),
    ]
    assert fuente["opciones"]["delimitador"] == ","

    detalle = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}")
    assert detalle.status_code == 200
    assert detalle.json()["id"] == fuente["id"]

    muestra = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/muestra?filas=5").json()
    assert muestra["columnas"] == ["id_venta", "fecha", "importe"]
    assert muestra["tipos"] == ["entero", "fecha", "decimal"]
    assert muestra["filas"] == [[1, "2026-01-05", 10.5], [2, "2026-01-06", 20.0]]
    assert muestra["total"] == 2

    guardados = almacen_temporal.listar(f"org_{datos.acme.id}/ws_{workspace_id}/")
    assert any(ruta.endswith(f"/fuentes/{fuente['id']}.parquet") for ruta in guardados)
    assert any("/subidas/" in ruta and ruta.endswith("Ventas_2026.csv") for ruta in guardados)


def test_resubir_reemplaza_la_misma_fuente(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    _procesar(cliente, cola, workspace_id, "ventas.csv", CSV_VENTAS)
    primera = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]

    tarea = _procesar(cliente, cola, workspace_id, "ventas.csv", b"IdVenta,Fecha,Importe,Sucursal\n1,2026-01-05,10.5,Centro\n2,2026-01-06,20,Norte\n3,2026-01-07,30,Oeste\n")
    assert tarea["resultado"]["fuentes"][0]["reemplazada"] is True

    # Resubida con deteccion de cambios (fase 4): el diff de esquema viaja en
    # el resultado de la tarea, con lo que cambio respecto de la version anterior.
    diff = tarea["resultado"]["fuentes"][0]["diff_esquema"]
    assert diff["columnas_nuevas"] == ["sucursal"]
    assert diff["columnas_perdidas"] == []
    assert diff["columnas_perdidas_en_uso"] == []
    assert diff["filas_antes"] == 2 and diff["filas_despues"] == 3

    fuentes = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()
    assert len(fuentes) == 1
    segunda = fuentes[0]
    assert segunda["id"] == primera["id"]
    assert segunda["filas"] == 3
    assert segunda["huella"] != primera["huella"]  # aparecio una columna
    assert [columna["nombre"] for columna in segunda["columnas"]][-1] == "sucursal"
    muestra = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{segunda['id']}/muestra").json()
    assert len(muestra["filas"]) == 3  # la vista DuckDB se reconstruyo


def test_subir_por_primera_vez_no_trae_diff(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    tarea = _procesar(cliente, cola, datos.acme_workspace_id, "ventas.csv", CSV_VENTAS)
    assert "diff_esquema" not in tarea["resultado"]["fuentes"][0]  # nada contra que comparar


def test_resubida_avisa_si_se_pierde_una_columna_que_el_modelo_usa(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    _procesar(cliente, cola, workspace_id, "ventas.csv", CSV_VENTAS)

    modelo = {
        "entidades": [
            {
                "id": "ventas",
                "nombre": "Ventas",
                "fuente": "ventas",
                "tipo": "hechos",
                "clave_primaria": ["id_venta"],
                "campos": [
                    {"id": "id_venta", "columna_origen": "id_venta", "nombre": "Id venta", "tipo_dato": "entero", "tipo_semantico": "identificador"},
                    {"id": "importe", "columna_origen": "importe", "nombre": "Importe", "tipo_dato": "decimal", "tipo_semantico": "monto"},
                ],
            }
        ]
    }
    respuesta_modelo = cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo)
    assert respuesta_modelo.status_code == 201, respuesta_modelo.text

    # La resubida se lleva "Importe" (que el modelo usa) y trae "Sucursal" nueva
    tarea = _procesar(cliente, cola, workspace_id, "ventas.csv", b"IdVenta,Fecha,Sucursal\n1,2026-01-05,Centro\n2,2026-01-06,Norte\n")
    diff = tarea["resultado"]["fuentes"][0]["diff_esquema"]
    assert diff["columnas_nuevas"] == ["sucursal"]
    assert "importe" in diff["columnas_perdidas"]
    assert diff["columnas_perdidas_en_uso"] == ["importe"]


def test_excel_con_dos_hojas_crea_dos_fuentes(cliente, datos, cola, ingresar):
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Vendedores"
    hoja.append(["Id", "Nombre"])
    hoja.append([1, "Ana"])
    otra = libro.create_sheet("Sucursales")
    otra.append(["Id", "Sucursal"])
    otra.append([1, "Centro"])
    buffer = io.BytesIO()
    libro.save(buffer)

    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    tarea = _procesar(cliente, cola, workspace_id, "maestros.xlsx", buffer.getvalue())
    assert [fuente["nombre_tabla"] for fuente in tarea["resultado"]["fuentes"]] == [
        "maestros_vendedores",
        "maestros_sucursales",
    ]
    fuentes = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()
    assert [(fuente["nombre_tabla"], fuente["hoja"], fuente["formato"]) for fuente in fuentes] == [
        ("maestros_sucursales", "Sucursales", "xlsx"),
        ("maestros_vendedores", "Vendedores", "xlsx"),
    ]


def test_roles_y_aislamiento(cliente, datos, cola, ingresar):
    workspace_id = datos.acme_workspace_id
    assert _subir(cliente, workspace_id, "v.csv", CSV_VENTAS).status_code == 401
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").status_code == 401

    ingresar("constructor@acme.test")
    _procesar(cliente, cola, workspace_id, "ventas.csv", CSV_VENTAS)
    fuente_id = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]["id"]
    cliente.post("/api/auth/logout")

    # El visualizador lee pero no escribe
    ingresar("visualizador@acme.test")
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").status_code == 200
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente_id}/muestra").status_code == 200
    prohibido = _subir(cliente, workspace_id, "v.csv", CSV_VENTAS)
    assert prohibido.status_code == 403
    assert prohibido.json()["codigo"] == "E-AUTH-03"
    assert cliente.delete(f"/api/workspaces/{workspace_id}/fuentes/{fuente_id}").status_code == 403
    cliente.post("/api/auth/logout")

    # Otra organizacion: el workspace no existe para ella
    ingresar("constructor@beta.test")
    ajeno = cliente.get(f"/api/workspaces/{workspace_id}/fuentes")
    assert ajeno.status_code == 404
    assert ajeno.json()["codigo"] == "E-WS-01"
    # Ni la fuente por id dentro de su propio workspace
    propio = cliente.get(f"/api/workspaces/{datos.beta_workspace_id}/fuentes/{fuente_id}")
    assert propio.status_code == 404
    assert propio.json()["codigo"] == "E-ING-04"


def test_archivos_invalidos_se_rechazan_antes_de_encolar(cliente, datos, cola, ingresar, monkeypatch):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id

    respuesta = _subir(cliente, workspace_id, "programa.exe", b"MZ...")
    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "E-ING-05"

    respuesta = _subir(cliente, workspace_id, "vacio.csv", b"  \n")
    assert respuesta.status_code == 400
    assert respuesta.json()["codigo"] == "E-ING-03"

    monkeypatch.setattr(obtener_configuracion(), "tamanio_maximo_archivo_mb", 0)
    respuesta = _subir(cliente, workspace_id, "grande.csv", CSV_VENTAS)
    assert respuesta.status_code == 413
    assert respuesta.json()["codigo"] == "E-ING-02"

    assert cliente.get(f"/api/workspaces/{workspace_id}/tareas").json() == []
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json() == []


def test_archivo_ilegible_deja_la_tarea_en_error(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    respuesta = _subir(cliente, workspace_id, "roto.xlsx", b"esto no es un excel")
    assert respuesta.status_code == 202
    tarea_id = respuesta.json()[0]["id"]
    cola.esperar(tarea_id, timeout=60)
    tarea = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea_id}").json()
    assert tarea["estado"] == "error"
    assert tarea["error"].startswith("E-ING-01: ")
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json() == []


def test_borrar_fuente(cliente, datos, cola, almacen_temporal, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    _procesar(cliente, cola, workspace_id, "ventas.csv", CSV_VENTAS)
    fuente = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]
    assert any(ruta.endswith(".parquet") for ruta in almacen_temporal.listar())

    assert cliente.delete(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}").status_code == 204
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json() == []
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}").status_code == 404
    assert almacen_temporal.listar() == []  # parquet y original borrados


def test_perfil_de_fuente(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    _procesar(cliente, cola, workspace_id, "ventas.csv", CSV_VENTAS)
    fuente = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]
    assert fuente["perfilada"] is True

    respuesta = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/perfil")
    assert respuesta.status_code == 200, respuesta.text
    perfil = respuesta.json()
    assert perfil["nombre_tabla"] == "ventas" and perfil["filas"] == 2
    assert perfil["candidatas_clave"] == ["id_venta"]
    por_nombre = {columna["nombre"]: columna for columna in perfil["columnas"]}
    assert por_nombre["id_venta"]["unica"] is True
    assert por_nombre["fecha"]["minimo"] == "2026-01-05" and por_nombre["fecha"]["maximo"] == "2026-01-06"
    assert por_nombre["importe"]["promedio"] == 15.25
    assert por_nombre["importe"]["top_valores"] == [{"valor": 10.5, "cantidad": 1}, {"valor": 20.0, "cantidad": 1}]

    # El visualizador tambien puede verlo (es lectura); otra organizacion, no
    ingresar("visualizador@acme.test")
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/perfil").status_code == 200
    ingresar("constructor@beta.test")
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/perfil").status_code == 404


def test_calidad_de_fuente(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    csv_sucio = b"IdVenta,Vendedor\n1,Ana\n2,\n3,\n4,\n"
    _procesar(cliente, cola, workspace_id, "ventas_sucias.csv", csv_sucio)
    fuente = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]

    respuesta = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/calidad")
    assert respuesta.status_code == 200, respuesta.text
    reporte = respuesta.json()
    assert reporte["fuente"] == "ventas_sucias" and reporte["filas"] == 4
    problema = next(p for p in reporte["problemas"] if p["codigo"] == "nulos_altos")
    assert problema["campo"] == "vendedor" and problema["severidad"] == "alta"  # 3 de 4 vacios

    # El visualizador tambien puede verlo (es lectura); otra organizacion, no
    ingresar("visualizador@acme.test")
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/calidad").status_code == 200
    ingresar("constructor@beta.test")
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/calidad").status_code == 404


def test_calidad_avisa_huerfanos_con_un_modelo_real_cargado(cliente, datos, cola, ingresar):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    _procesar(cliente, cola, workspace_id, "ventas.csv", b"IdVenta,IdVendedor\n1,1\n2,1\n3,99\n")
    _procesar(cliente, cola, workspace_id, "vendedores.csv", b"IdVendedor,Nombre\n1,Ana\n2,Bruno\n")
    fuentes = {fuente["nombre_tabla"]: fuente for fuente in cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()}

    modelo = {
        "entidades": [
            {
                "id": "ventas",
                "nombre": "Ventas",
                "fuente": "ventas",
                "tipo": "hechos",
                "clave_primaria": ["id_venta"],
                "campos": [
                    {"id": "id_venta", "columna_origen": "id_venta", "nombre": "Id venta", "tipo_dato": "entero", "tipo_semantico": "identificador"},
                    {"id": "id_vendedor", "columna_origen": "id_vendedor", "nombre": "Vendedor", "tipo_dato": "entero", "tipo_semantico": "clave_foranea"},
                ],
            },
            {
                "id": "vendedores",
                "nombre": "Vendedores",
                "fuente": "vendedores",
                "tipo": "dimension",
                "clave_primaria": ["id_vendedor"],
                "campos": [{"id": "id_vendedor", "columna_origen": "id_vendedor", "nombre": "Id vendedor", "tipo_dato": "entero", "tipo_semantico": "identificador"}],
            },
        ],
        "relaciones": [{"id": "r1", "desde": {"entidad": "ventas", "campo": "id_vendedor"}, "hacia": {"entidad": "vendedores", "campo": "id_vendedor"}}],
    }
    respuesta_modelo = cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo)
    assert respuesta_modelo.status_code == 201, respuesta_modelo.text

    reporte = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuentes['ventas']['id']}/calidad").json()
    problema = next(p for p in reporte["problemas"] if p["codigo"] == "huerfanos")
    assert problema["detalle"]["huerfanos"] == 1 and problema["detalle"]["hacia"] == "vendedores"


RECETA_ANCHO_FIJO = {
    "modo": "ancho_fijo",
    "columnas": [{"nombre": "id", "inicio": 0, "fin": 3}, {"nombre": "nombre", "inicio": 3, "fin": 15}],
}
LINEA_ANCHO_FIJO = f"{100:03d}{'Ana Martinez':<12}"  # sin 0 adelante: tipa como entero, no como codigo


def test_estructura_proponer_y_confirmar_ingesta_con_la_receta(cliente, datos, cola, ingresar, llm_falso):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    llm_falso([RECETA_ANCHO_FIJO])

    propuesta = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/proponer",
        files=[("archivo", ("reporte.txt", LINEA_ANCHO_FIJO.encode(), "text/plain"))],
    )
    assert propuesta.status_code == 202, propuesta.text
    tarea_id = propuesta.json()["id"]
    cola.esperar(tarea_id, timeout=60)
    tarea_propuesta = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea_id}").json()
    assert tarea_propuesta["estado"] == "terminada", tarea_propuesta
    assert tarea_propuesta["resultado"]["receta"]["modo"] == "ancho_fijo"
    assert tarea_propuesta["resultado"]["muestra"] == [LINEA_ANCHO_FIJO]
    assert tarea_propuesta["resultado"]["claude"]["usado"] is True

    # Nada se ingesto todavia: sin fuentes hasta confirmar
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json() == []

    confirmacion = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/confirmar",
        json={"tarea_id": tarea_id, "receta": RECETA_ANCHO_FIJO},
    )
    assert confirmacion.status_code == 202, confirmacion.text
    tarea_ingesta_id = confirmacion.json()["id"]
    cola.esperar(tarea_ingesta_id, timeout=60)
    tarea_ingesta = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea_ingesta_id}").json()
    assert tarea_ingesta["estado"] == "terminada", tarea_ingesta
    assert tarea_ingesta["tipo"] == "ingesta.procesar_archivo"

    fuentes = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()
    assert len(fuentes) == 1
    fuente = fuentes[0]
    assert fuente["formato"] == "texto"
    assert [(columna["nombre"], columna["tipo"]) for columna in fuente["columnas"]] == [("id", "entero"), ("nombre", "texto")]
    muestra = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/muestra").json()
    assert muestra["filas"] == [[100, "Ana Martinez"]]


def test_estructura_confirmar_con_receta_ajustada_por_la_persona(cliente, datos, cola, ingresar, llm_falso):
    """La persona puede tocar la receta antes de confirmar (ej. renombrar una
    columna): se ingesta con la receta final, no con la que propuso Claude."""
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    llm_falso([RECETA_ANCHO_FIJO])

    propuesta = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/proponer",
        files=[("archivo", ("reporte.txt", LINEA_ANCHO_FIJO.encode(), "text/plain"))],
    )
    tarea_id = propuesta.json()["id"]
    cola.esperar(tarea_id, timeout=60)

    receta_ajustada = {**RECETA_ANCHO_FIJO, "columnas": [{"nombre": "id_empleado", "inicio": 0, "fin": 3}, {"nombre": "nombre", "inicio": 3, "fin": 15}]}
    confirmacion = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/confirmar",
        json={"tarea_id": tarea_id, "receta": receta_ajustada},
    )
    cola.esperar(confirmacion.json()["id"], timeout=60)
    fuente = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]
    assert [columna["nombre"] for columna in fuente["columnas"]] == ["id_empleado", "nombre"]


def test_estructura_confirmar_con_tarea_ajena_o_inexistente_no_pasa(cliente, datos, cola, ingresar, llm_falso):
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id

    # Tarea que no existe
    respuesta = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/confirmar",
        json={"tarea_id": "no-existe", "receta": RECETA_ANCHO_FIJO},
    )
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "E-TAREA-01"

    # Tarea de OTRO workspace: tampoco (no se puede reusar su ruta_original)
    llm_falso([RECETA_ANCHO_FIJO])
    propuesta = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/proponer",
        files=[("archivo", ("reporte.txt", LINEA_ANCHO_FIJO.encode(), "text/plain"))],
    )
    tarea_id = propuesta.json()["id"]
    cola.esperar(tarea_id, timeout=60)
    cliente.post("/api/auth/logout")
    ingresar("constructor@beta.test")
    ajeno = cliente.post(
        f"/api/workspaces/{datos.beta_workspace_id}/fuentes/estructura/confirmar",
        json={"tarea_id": tarea_id, "receta": RECETA_ANCHO_FIJO},
    )
    assert ajeno.status_code == 404
    assert ajeno.json()["codigo"] == "E-TAREA-01"


def test_estructura_proponer_sin_clave_de_claude_e_inf_07(cliente, datos, cola, ingresar, monkeypatch):
    import app.inferencia.tarea as inferencia_tarea

    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    # A diferencia de llm_falso (respuestas grabadas), acá se simula que no
    # hay clave configurada en absoluto: obtener_cliente_llm() -> None.
    monkeypatch.setattr(inferencia_tarea, "obtener_cliente_llm", lambda: None)

    propuesta = cliente.post(
        f"/api/workspaces/{workspace_id}/fuentes/estructura/proponer",
        files=[("archivo", ("reporte.txt", LINEA_ANCHO_FIJO.encode(), "text/plain"))],
    )
    tarea_id = propuesta.json()["id"]
    cola.esperar(tarea_id, timeout=60)
    tarea = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea_id}").json()
    assert tarea["estado"] == "error"
    assert tarea["error"].startswith("E-INF-07: ")


def test_fuente_sin_perfil_responde_e_ing_06(cliente, datos, cola, ingresar, sesion_db):
    from app.catalogo.tablas import Fuente

    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    _procesar(cliente, cola, workspace_id, "ventas.csv", CSV_VENTAS)
    fuente = cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]
    fila = sesion_db.get(Fuente, fuente["id"])
    fila.perfil = None  # como una fuente ingestada antes del paso 9
    sesion_db.commit()
    assert cliente.get(f"/api/workspaces/{workspace_id}/fuentes").json()[0]["perfilada"] is False
    respuesta = cliente.get(f"/api/workspaces/{workspace_id}/fuentes/{fuente['id']}/perfil")
    assert respuesta.status_code == 404
    assert respuesta.json()["codigo"] == "E-ING-06"
