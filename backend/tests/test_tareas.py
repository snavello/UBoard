"""Cola local de tareas: ciclo de vida de la fila, errores, huerfanas y el
endpoint de polling con aislamiento por workspace."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from app.catalogo.tablas import EstadoTarea, Tarea
from app.nucleo.errores import ErrorApp
from app.tareas import ContextoTarea, encolar_tarea, marcar_tareas_huerfanas, obtener_manejador, registrar_tarea

# Manejadores de prueba; se registran una vez al importar el modulo


@registrar_tarea("prueba.suma")
def _suma(contexto: ContextoTarea, parametros: dict) -> dict:
    contexto.informar(50, "sumando")
    return {"total": parametros["a"] + parametros["b"]}


@registrar_tarea("prueba.error_esperado")
def _error_esperado(contexto: ContextoTarea, parametros: dict) -> dict:
    raise ErrorApp("E-ALM-02", "archivo.csv")


@registrar_tarea("prueba.explota")
def _explota(contexto: ContextoTarea, parametros: dict) -> dict:
    raise RuntimeError("kaboom")


def _releer(sesion_db, tarea_id: str) -> Tarea:
    sesion_db.expire_all()
    return sesion_db.get(Tarea, tarea_id)


def test_el_registro_rechaza_duplicados_y_tipos_desconocidos():
    with pytest.raises(ValueError):
        registrar_tarea("prueba.suma")(lambda contexto, parametros: None)
    with pytest.raises(ErrorApp) as error:
        obtener_manejador("no.existe")
    assert error.value.codigo == "E-TAREA-02"


def test_tarea_exitosa_deja_resultado_progreso_y_tiempos(sesion_db, datos, cola):
    workspace = datos.acme.workspaces[0]
    tarea = encolar_tarea(
        sesion_db, cola, tipo="prueba.suma", parametros={"a": 2, "b": 3}, workspace=workspace, usuario=datos.acme_constructor
    )
    assert tarea.estado == EstadoTarea.PENDIENTE
    assert tarea.creada_en is not None
    cola.esperar(tarea.id, timeout=10)

    fila = _releer(sesion_db, tarea.id)
    assert fila.estado == EstadoTarea.TERMINADA
    assert fila.progreso == 100
    assert fila.resultado == {"total": 5}
    assert fila.mensaje == "sumando"
    assert fila.error is None
    assert fila.iniciada_en is not None and fila.terminada_en is not None
    assert fila.creada_por_id == datos.acme_constructor.id
    assert fila.workspace_id == workspace.id


def test_un_error_esperado_queda_con_su_codigo(sesion_db, datos, cola):
    tarea = encolar_tarea(sesion_db, cola, tipo="prueba.error_esperado", workspace=datos.acme.workspaces[0])
    cola.esperar(tarea.id, timeout=10)
    fila = _releer(sesion_db, tarea.id)
    assert fila.estado == EstadoTarea.ERROR
    assert fila.error.startswith("E-ALM-02: ")
    assert "archivo.csv" in fila.error
    assert fila.resultado is None
    assert fila.terminada_en is not None


def test_una_excepcion_inesperada_no_tumba_la_cola(sesion_db, datos, cola):
    workspace = datos.acme.workspaces[0]
    rota = encolar_tarea(sesion_db, cola, tipo="prueba.explota", workspace=workspace)
    cola.esperar(rota.id, timeout=10)
    fila = _releer(sesion_db, rota.id)
    assert fila.estado == EstadoTarea.ERROR
    assert fila.error.startswith("E-INTERNO-00 ref=")
    assert "RuntimeError" in fila.error

    # La siguiente tarea corre normal
    sana = encolar_tarea(sesion_db, cola, tipo="prueba.suma", parametros={"a": 1, "b": 1}, workspace=workspace)
    cola.esperar(sana.id, timeout=10)
    assert _releer(sesion_db, sana.id).estado == EstadoTarea.TERMINADA


def test_encolar_un_tipo_desconocido_no_crea_fila(sesion_db, datos, cola):
    with pytest.raises(ErrorApp) as error:
        encolar_tarea(sesion_db, cola, tipo="no.existe", workspace=datos.acme.workspaces[0])
    assert error.value.codigo == "E-TAREA-02"
    assert sesion_db.scalar(select(func.count()).select_from(Tarea)) == 0


def test_marcar_tareas_huerfanas(sesion_db, datos):
    workspace_id = datos.acme.workspaces[0].id
    pendiente = Tarea(tipo="prueba.suma", estado=EstadoTarea.PENDIENTE, workspace_id=workspace_id)
    corriendo = Tarea(tipo="prueba.suma", estado=EstadoTarea.CORRIENDO, workspace_id=workspace_id, progreso=40)
    terminada = Tarea(
        tipo="prueba.suma", estado=EstadoTarea.TERMINADA, workspace_id=workspace_id, progreso=100,
        terminada_en=datetime.now(timezone.utc),
    )
    sesion_db.add_all([pendiente, corriendo, terminada])
    sesion_db.commit()

    assert marcar_tareas_huerfanas(sesion_db) == 2
    assert _releer(sesion_db, pendiente.id).estado == EstadoTarea.ERROR
    assert _releer(sesion_db, corriendo.id).error.startswith("E-TAREA-03: ")
    assert _releer(sesion_db, terminada.id).estado == EstadoTarea.TERMINADA
    # Segunda pasada: nada que marcar
    assert marcar_tareas_huerfanas(sesion_db) == 0


def test_polling_de_una_tarea_respeta_el_workspace(cliente, sesion_db, datos, cola, ingresar):
    workspace = datos.acme.workspaces[0]
    tarea = encolar_tarea(sesion_db, cola, tipo="prueba.suma", parametros={"a": 1, "b": 1}, workspace=workspace)
    cola.esperar(tarea.id, timeout=10)
    ruta = f"/api/workspaces/{workspace.id}/tareas/{tarea.id}"

    assert cliente.get(ruta).status_code == 401

    ingresar("constructor@acme.test")
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "terminada"
    assert cuerpo["progreso"] == 100
    assert cuerpo["resultado"] == {"total": 2}
    assert cuerpo["tipo"] == "prueba.suma"

    listado = cliente.get(f"/api/workspaces/{workspace.id}/tareas")
    assert [tarea_listada["id"] for tarea_listada in listado.json()] == [tarea.id]

    # La misma tarea buscada en el workspace de otra organizacion: no existe
    ajena = cliente.get(f"/api/workspaces/{datos.beta_workspace_id}/tareas/{tarea.id}")
    assert ajena.status_code == 404
    assert ajena.json()["codigo"] == "E-WS-01"

    inexistente = cliente.get(f"/api/workspaces/{workspace.id}/tareas/00000000-0000-0000-0000-000000000000")
    assert inexistente.status_code == 404
    assert inexistente.json()["codigo"] == "E-TAREA-01"

    # El visualizador de la misma organizacion puede seguir el progreso
    cliente.post("/api/auth/logout")
    ingresar("visualizador@acme.test")
    assert cliente.get(ruta).status_code == 200

    # Un constructor de otra organizacion, no: el workspace es ajeno
    cliente.post("/api/auth/logout")
    ingresar("constructor@beta.test")
    assert cliente.get(ruta).status_code == 404
    # Ni buscando la tarea ajena dentro de su propio workspace
    propia_ruta = cliente.get(f"/api/workspaces/{datos.beta_workspace_id}/tareas/{tarea.id}")
    assert propia_ruta.json()["codigo"] == "E-TAREA-01"


def test_el_listado_va_de_la_mas_reciente_a_la_mas_vieja(cliente, sesion_db, datos, cola, ingresar):
    workspace = datos.acme.workspaces[0]
    ids = [
        encolar_tarea(sesion_db, cola, tipo="prueba.suma", parametros={"a": i, "b": 0}, workspace=workspace).id
        for i in range(3)
    ]
    for tarea_id in ids:
        cola.esperar(tarea_id, timeout=10)
    ingresar("constructor@acme.test")
    listado = cliente.get(f"/api/workspaces/{workspace.id}/tareas?limite=2").json()
    assert [tarea["id"] for tarea in listado] == ids[::-1][:2]
    assert [tarea["resultado"]["total"] for tarea in listado] == [2, 1]
