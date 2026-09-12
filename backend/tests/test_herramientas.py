"""Catalogo de herramientas del asistente (paso 19): la forma del catalogo
segun el rol (puro, sin base) y la ejecucion real de unas pocas herramientas
contra los 5 CSV cargados, para confirmar que cada una hace lo mismo que su
endpoint de siempre."""
import pytest

from app.asistente.herramientas import catalogo_para_rol
from app.catalogo.tablas import RolUsuario, Workspace
from app.nucleo.errores import ErrorApp


# ---------- Forma del catalogo (puro: las funciones no se ejecutan) ----------
def test_catalogo_constructor_tiene_las_35_operaciones_mas_consultar_y_restaurar():
    catalogo = catalogo_para_rol(RolUsuario.CONSTRUCTOR, sesion=None, workspace=None, almacen=None, usuario=None)
    nombres = [definicion["name"] for definicion in catalogo.definiciones]
    assert len(nombres) == len(set(nombres)) == 37
    assert {"consultar", "restaurar_version", "crear_metrica", "crear_grafico", "confirmar_todo"} <= set(nombres)
    crear_metrica = next(d for d in catalogo.definiciones if d["name"] == "crear_metrica")
    assert "operacion" not in crear_metrica["input_schema"]["properties"], "el nombre de la herramienta ya lo dice"
    assert "expresion" in crear_metrica["input_schema"]["properties"]


def test_catalogo_visualizador_solo_consultar():
    catalogo = catalogo_para_rol(RolUsuario.VISUALIZADOR, sesion=None, workspace=None, almacen=None, usuario=None)
    assert [definicion["name"] for definicion in catalogo.definiciones] == ["consultar"]


def test_ejecutar_herramienta_desconocida():
    catalogo = catalogo_para_rol(RolUsuario.VISUALIZADOR, sesion=None, workspace=None, almacen=None, usuario=None)
    with pytest.raises(ErrorApp) as error:
        catalogo.ejecutar("crear_metrica", {})
    assert error.value.codigo == "E-ASI-03"


# ---------- Ejecucion real ----------
@pytest.fixture
def workspace_listo(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, spec_prueba, sesion_db) -> Workspace:
    """Constructor de Acme logueado, con fuentes, modelo y spec cargados de
    verdad (mismo fixture que usan los tests de la API)."""
    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201
    assert cliente.put(f"/api/workspaces/{workspace_id}/dashboard", json=spec_prueba).status_code == 201
    return sesion_db.get(Workspace, workspace_id)


def test_herramienta_de_operacion_del_modelo_crea_una_version(workspace_listo, datos, sesion_db, almacen_temporal):
    from app.modelo import operaciones as modelo_operaciones

    catalogo = catalogo_para_rol(
        RolUsuario.CONSTRUCTOR, sesion=sesion_db, workspace=workspace_listo, almacen=almacen_temporal, usuario=datos.acme_constructor
    )
    resultado = catalogo.ejecutar("crear_metrica", {"id": "descuento_total", "nombre": "Descuento total", "expresion": {"agregacion": "suma", "campo": "ventas.precio_unitario"}})
    assert "versión 2 del modelo" in resultado
    actual = modelo_operaciones.exigir_version_actual(sesion_db, workspace_listo)
    assert actual.numero == 2 and modelo_operaciones.modelo_de(actual).metrica("descuento_total") is not None


def test_herramienta_de_operacion_del_dashboard_crea_una_version(workspace_listo, datos, sesion_db, almacen_temporal):
    from app.dashboard import operaciones as dashboard_operaciones

    catalogo = catalogo_para_rol(
        RolUsuario.CONSTRUCTOR, sesion=sesion_db, workspace=workspace_listo, almacen=almacen_temporal, usuario=datos.acme_constructor
    )
    resultado = catalogo.ejecutar("crear_kpi", {"metrica": "cantidad_ventas", "titulo": "Cantidad"})
    assert "versión 2 del dashboard" in resultado
    actual = dashboard_operaciones.exigir_version_actual(sesion_db, workspace_listo)
    assert any(kpi.titulo == "Cantidad" for kpi in dashboard_operaciones.spec_de(actual).kpis)


def test_herramienta_operacion_invalida_levanta_error_app(workspace_listo, datos, sesion_db, almacen_temporal):
    catalogo = catalogo_para_rol(
        RolUsuario.CONSTRUCTOR, sesion=sesion_db, workspace=workspace_listo, almacen=almacen_temporal, usuario=datos.acme_constructor
    )
    with pytest.raises(ErrorApp) as error:
        catalogo.ejecutar("eliminar_metrica", {"metrica": "no_existe"})
    assert error.value.codigo == "E-MOD-05"


def test_herramienta_consultar_devuelve_datos_reales(workspace_listo, datos, sesion_db, almacen_temporal):
    catalogo = catalogo_para_rol(
        RolUsuario.VISUALIZADOR, sesion=sesion_db, workspace=workspace_listo, almacen=almacen_temporal, usuario=datos.acme_visualizador
    )
    resultado = catalogo.ejecutar("consultar", {"metricas": ["total_ventas", "cantidad_ventas"]})
    assert '"cantidad_ventas"' in resultado and '"filas"' in resultado
    import json

    cuerpo = json.loads(resultado)
    assert cuerpo["filas"][0][1] == 3000


def test_herramienta_consultar_respeta_filtros_base(workspace_listo, datos, sesion_db, almacen_temporal):
    from app.consultas.esquema import FiltroConsulta

    catalogo = catalogo_para_rol(
        RolUsuario.VISUALIZADOR,
        sesion=sesion_db,
        workspace=workspace_listo,
        almacen=almacen_temporal,
        usuario=datos.acme_visualizador,
        filtros_base=[FiltroConsulta(campo="vendedores.nombre", operador="igual", valor="nadie existe")],
    )
    import json

    resultado = json.loads(catalogo.ejecutar("consultar", {"metricas": ["cantidad_ventas"], "dimensiones": [{"campo": "vendedores.nombre"}]}))
    assert resultado["filas"] == []


def test_herramienta_restaurar_version(workspace_listo, datos, sesion_db, almacen_temporal):
    from app.modelo import operaciones as modelo_operaciones

    catalogo = catalogo_para_rol(
        RolUsuario.CONSTRUCTOR, sesion=sesion_db, workspace=workspace_listo, almacen=almacen_temporal, usuario=datos.acme_constructor
    )
    catalogo.ejecutar("crear_metrica", {"id": "x", "nombre": "X", "expresion": {"agregacion": "conteo", "campo": "ventas.id_venta"}})
    resultado = catalogo.ejecutar("restaurar_version", {"artefacto": "modelo", "numero": 1})
    assert "Se restauró la versión 1 del modelo" in resultado
    actual = modelo_operaciones.exigir_version_actual(sesion_db, workspace_listo)
    assert actual.numero == 3 and modelo_operaciones.modelo_de(actual).metrica("x") is None
