"""Login, cookie de sesion, vencimiento, renovacion y bloqueos."""
from datetime import datetime, timedelta, timezone

import jwt

from app.nucleo import auth
from tests.conftest import CLAVE


def test_hashear_y_verificar_clave():
    hash_1 = auth.hashear_clave("secreta-123")
    assert auth.verificar_clave("secreta-123", hash_1)
    assert not auth.verificar_clave("otra", hash_1)
    # Sal distinta en cada hash: dos usuarios con la misma clave no comparten hash
    assert hash_1 != auth.hashear_clave("secreta-123")
    assert not auth.verificar_clave("x", "basura-sin-separador")
    assert not auth.verificar_clave("x", "")


def test_login_correcto_setea_cookie_y_devuelve_usuario(cliente, datos):
    # El email se normaliza: espacios y mayusculas no importan
    respuesta = cliente.post("/api/auth/login", json={"email": "  Constructor@ACME.test ", "clave": CLAVE})
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["email"] == "constructor@acme.test"
    assert cuerpo["rol"] == "constructor"
    assert cuerpo["organizacion"]["nombre"] == "Acme"
    assert cuerpo["workspace_id"] == datos.acme_workspace_id
    assert auth.NOMBRE_COOKIE in respuesta.cookies
    cabecera = respuesta.headers["set-cookie"].lower()
    assert "httponly" in cabecera
    assert "samesite=lax" in cabecera
    assert "path=/" in cabecera


def test_login_rechaza_clave_incorrecta_y_email_inexistente_con_el_mismo_error(cliente, datos):
    mala_clave = cliente.post("/api/auth/login", json={"email": "constructor@acme.test", "clave": "incorrecta"})
    sin_usuario = cliente.post("/api/auth/login", json={"email": "nadie@acme.test", "clave": CLAVE})
    assert mala_clave.status_code == 401
    assert sin_usuario.status_code == 401
    assert mala_clave.json()["codigo"] == "E-AUTH-01"
    # Misma respuesta: no se revela cuales emails existen
    assert mala_clave.json() == sin_usuario.json()
    assert auth.NOMBRE_COOKIE not in mala_clave.cookies


def test_yo_sin_sesion(cliente):
    respuesta = cliente.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "E-AUTH-02"


def test_yo_con_sesion_devuelve_usuario_y_renueva_la_cookie(cliente, datos, ingresar):
    ingresar("visualizador@acme.test")
    respuesta = cliente.get("/api/auth/yo")
    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == "visualizador@acme.test"
    assert respuesta.json()["rol"] == "visualizador"
    # Renovacion deslizante: cada request autenticado reemite la cookie
    assert auth.NOMBRE_COOKIE in respuesta.cookies


def test_logout_cierra_la_sesion(cliente, datos, ingresar):
    ingresar("constructor@acme.test")
    assert cliente.get("/api/auth/yo").status_code == 200
    assert cliente.post("/api/auth/logout").status_code == 200
    assert cliente.get("/api/auth/yo").status_code == 401


def test_token_vencido_no_sirve(cliente, datos):
    hace_dos_horas = datetime.now(timezone.utc) - timedelta(hours=2)
    vencido = auth.crear_token(datos.acme_constructor, ahora=hace_dos_horas)
    cliente.cookies.set(auth.NOMBRE_COOKIE, vencido)
    respuesta = cliente.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "E-AUTH-02"


def test_token_firmado_con_otro_secreto_no_sirve(cliente, datos):
    ahora = datetime.now(timezone.utc)
    ajeno = jwt.encode(
        {"sub": str(datos.acme_constructor.id), "rol": "constructor", "iat": ahora, "exp": ahora + timedelta(minutes=10)},
        "otro-secreto",
        algorithm=auth.ALGORITMO_JWT,
    )
    cliente.cookies.set(auth.NOMBRE_COOKIE, ajeno)
    assert cliente.get("/api/auth/yo").status_code == 401


def test_token_de_usuario_borrado_no_sirve(cliente, datos, sesion_db):
    token = auth.crear_token(datos.beta_constructor)
    sesion_db.delete(datos.beta_constructor)
    sesion_db.commit()
    cliente.cookies.set(auth.NOMBRE_COOKIE, token)
    assert cliente.get("/api/auth/yo").status_code == 401


def test_usuario_desactivado_no_entra_ni_conserva_la_sesion(cliente, datos, sesion_db, ingresar):
    ingresar("visualizador@acme.test")
    datos.acme_visualizador.activo = False
    sesion_db.commit()
    # La sesion ya abierta deja de servir en el siguiente request
    respuesta = cliente.get("/api/auth/yo")
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "E-AUTH-04"
    # Y tampoco puede volver a ingresar
    respuesta = cliente.post("/api/auth/login", json={"email": "visualizador@acme.test", "clave": CLAVE})
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "E-AUTH-04"


def test_organizacion_desactivada_bloquea_a_sus_usuarios_pero_no_a_plataforma(cliente, datos, sesion_db):
    datos.acme.activa = False
    sesion_db.commit()
    respuesta = cliente.post("/api/auth/login", json={"email": "constructor@acme.test", "clave": CLAVE})
    assert respuesta.status_code == 401
    assert respuesta.json()["codigo"] == "E-AUTH-05"
    respuesta = cliente.post("/api/auth/login", json={"email": "admin@uboard.test", "clave": CLAVE})
    assert respuesta.status_code == 200
    assert respuesta.json()["organizacion"] is None
    assert respuesta.json()["workspace_id"] is None
