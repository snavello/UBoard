"""Reglas de altas y bajas del catalogo, probadas sin HTTP."""
import pytest

from app.catalogo import operaciones
from app.catalogo.tablas import RolUsuario
from app.nucleo.errores import ErrorApp
from tests.conftest import CLAVE


@pytest.mark.parametrize(
    "entrada, esperado",
    [
        ("  Ana@Acme.COM ", "ana@acme.com"),
        ("luis@sub.dominio.ar", "luis@sub.dominio.ar"),
    ],
)
def test_normalizar_email(entrada, esperado):
    assert operaciones.normalizar_email(entrada) == esperado


@pytest.mark.parametrize("invalido", ["", "sin-arroba", "@dominio.com", "ana@", "ana@dominio", "ana@.com", "ana@dominio."])
def test_normalizar_email_rechaza_invalidos(invalido):
    with pytest.raises(ErrorApp) as error:
        operaciones.normalizar_email(invalido)
    assert error.value.codigo == "E-PLAT-07"


def test_crear_organizacion_nace_con_workspace_principal(sesion_db):
    organizacion = operaciones.crear_organizacion(sesion_db, "Acme")
    assert [workspace.nombre for workspace in organizacion.workspaces] == ["Principal"]
    assert operaciones.workspace_principal(organizacion) is organizacion.workspaces[0]
    assert operaciones.workspace_principal(None) is None


def test_rol_y_organizacion_tienen_que_ser_coherentes(sesion_db):
    organizacion = operaciones.crear_organizacion(sesion_db, "Acme")
    with pytest.raises(ValueError):
        operaciones.crear_usuario(
            sesion_db, email="a@acme.test", nombre="A", clave=CLAVE, rol=RolUsuario.PLATAFORMA, organizacion=organizacion
        )
    with pytest.raises(ValueError):
        operaciones.crear_usuario(sesion_db, email="b@acme.test", nombre="B", clave=CLAVE, rol=RolUsuario.CONSTRUCTOR)


def test_la_clave_no_se_guarda_en_claro(sesion_db):
    usuario = operaciones.crear_usuario(
        sesion_db, email="admin@uboard.test", nombre="Admin", clave=CLAVE, rol=RolUsuario.PLATAFORMA
    )
    assert CLAVE not in usuario.clave_hash
    assert "$" in usuario.clave_hash


def test_no_se_desactiva_al_ultimo_admin_de_plataforma(sesion_db):
    admin = operaciones.crear_usuario(
        sesion_db, email="admin@uboard.test", nombre="Admin", clave=CLAVE, rol=RolUsuario.PLATAFORMA
    )
    organizacion = operaciones.crear_organizacion(sesion_db, "Acme")
    constructor = operaciones.crear_usuario(
        sesion_db, email="c@acme.test", nombre="C", clave=CLAVE, rol=RolUsuario.CONSTRUCTOR, organizacion=organizacion
    )
    with pytest.raises(ErrorApp) as error:
        operaciones.cambiar_activo(sesion_db, admin, False, quien=constructor)
    assert error.value.codigo == "E-PLAT-05"
    assert admin.activo is True

    # Con un segundo admin activo, si se puede
    operaciones.crear_usuario(sesion_db, email="otro@uboard.test", nombre="Otro", clave=CLAVE, rol=RolUsuario.PLATAFORMA)
    operaciones.cambiar_activo(sesion_db, admin, False, quien=constructor)
    assert admin.activo is False
