"""API de plataforma: solo el rol plataforma; altas de organizaciones y usuarios."""
from tests.conftest import CLAVE


def test_anonimo_y_roles_sin_permiso(cliente, datos, ingresar):
    assert cliente.get("/api/plataforma/organizaciones").status_code == 401

    ingresar("constructor@acme.test")
    respuesta = cliente.get("/api/plataforma/organizaciones")
    assert respuesta.status_code == 403
    assert respuesta.json()["codigo"] == "E-AUTH-03"
    # Tampoco las de escritura
    assert cliente.post("/api/plataforma/organizaciones", json={"nombre": "X"}).status_code == 403

    cliente.post("/api/auth/logout")
    ingresar("visualizador@acme.test")
    assert cliente.get("/api/plataforma/organizaciones").status_code == 403


def test_admin_lista_y_crea_organizaciones(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    respuesta = cliente.get("/api/plataforma/organizaciones")
    assert respuesta.status_code == 200
    organizaciones = respuesta.json()
    assert [organizacion["nombre"] for organizacion in organizaciones] == ["Acme", "Beta"]
    acme = organizaciones[0]
    assert acme["cantidad_usuarios"] == 2
    assert acme["workspace_id"] == datos.acme_workspace_id

    respuesta = cliente.post("/api/plataforma/organizaciones", json={"nombre": "  Gamma  "})
    assert respuesta.status_code == 201, respuesta.text
    gamma = respuesta.json()
    assert gamma["nombre"] == "Gamma"
    assert gamma["workspace_id"] is not None  # nace con su workspace
    assert gamma["cantidad_usuarios"] == 0

    # Repetida (sin distinguir mayusculas) y vacia
    repetida = cliente.post("/api/plataforma/organizaciones", json={"nombre": "gamma"})
    assert repetida.status_code == 409
    assert repetida.json()["codigo"] == "E-PLAT-01"
    assert cliente.post("/api/plataforma/organizaciones", json={"nombre": "   "}).status_code == 409


def test_admin_crea_usuarios_en_una_organizacion(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    ruta = f"/api/plataforma/organizaciones/{datos.acme.id}/usuarios"
    nuevo = {"email": "Nuevo@Acme.test", "nombre": "Nuevo", "clave": "clave-nueva-123", "rol": "visualizador"}
    respuesta = cliente.post(ruta, json=nuevo)
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["email"] == "nuevo@acme.test"
    assert respuesta.json()["organizacion"]["id"] == datos.acme.id
    assert respuesta.json()["workspace_id"] == datos.acme_workspace_id

    duplicado = cliente.post(ruta, json=nuevo)
    assert duplicado.status_code == 409
    assert duplicado.json()["codigo"] == "E-PLAT-02"

    corta = cliente.post(ruta, json={**nuevo, "email": "otro@acme.test", "clave": "corta"})
    assert corta.status_code == 400
    assert corta.json()["codigo"] == "E-PLAT-06"

    invalido = cliente.post(ruta, json={**nuevo, "email": "sin-arroba"})
    assert invalido.status_code == 400
    assert invalido.json()["codigo"] == "E-PLAT-07"

    # El rol plataforma no se crea por esta ruta
    assert cliente.post(ruta, json={**nuevo, "email": "x@acme.test", "rol": "plataforma"}).status_code == 422

    inexistente = cliente.post("/api/plataforma/organizaciones/99999/usuarios", json=nuevo)
    assert inexistente.status_code == 404
    assert inexistente.json()["codigo"] == "E-PLAT-03"

    listado = cliente.get(ruta)
    assert [usuario["email"] for usuario in listado.json()] == [
        "constructor@acme.test",
        "visualizador@acme.test",
        "nuevo@acme.test",
    ]

    # El usuario nuevo puede entrar
    cliente.post("/api/auth/logout")
    ingresar("nuevo@acme.test", "clave-nueva-123")


def test_admin_desactiva_y_reactiva_un_usuario(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    ruta = f"/api/plataforma/usuarios/{datos.acme_visualizador.id}"
    respuesta = cliente.patch(ruta, json={"activo": False})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["activo"] is False

    cliente.post("/api/auth/logout")
    bloqueado = cliente.post("/api/auth/login", json={"email": "visualizador@acme.test", "clave": CLAVE})
    assert bloqueado.status_code == 401
    assert bloqueado.json()["codigo"] == "E-AUTH-04"

    ingresar("admin@uboard.test")
    assert cliente.patch(ruta, json={"activo": True}).json()["activo"] is True
    cliente.post("/api/auth/logout")
    ingresar("visualizador@acme.test")


def test_admin_no_se_desactiva_a_si_mismo_y_puede_crear_otros_admins(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    propio = cliente.patch(f"/api/plataforma/usuarios/{datos.admin.id}", json={"activo": False})
    assert propio.status_code == 400
    assert propio.json()["codigo"] == "E-PLAT-08"

    respuesta = cliente.post(
        "/api/plataforma/administradores",
        json={"email": "segundo@uboard.test", "nombre": "Segundo", "clave": "clave-segundo-123"},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["rol"] == "plataforma"
    assert respuesta.json()["organizacion"] is None
    segundo_id = respuesta.json()["id"]

    administradores = cliente.get("/api/plataforma/administradores").json()
    assert [administrador["email"] for administrador in administradores] == ["admin@uboard.test", "segundo@uboard.test"]

    # Un admin no cambia de rol
    assert cliente.patch(f"/api/plataforma/usuarios/{segundo_id}", json={"rol": "constructor"}).status_code == 403

    # Con dos activos, se puede desactivar al otro
    assert cliente.patch(f"/api/plataforma/usuarios/{segundo_id}", json={"activo": False}).json()["activo"] is False

    inexistente = cliente.patch("/api/plataforma/usuarios/99999", json={"activo": False})
    assert inexistente.status_code == 404
    assert inexistente.json()["codigo"] == "E-PLAT-04"


def test_admin_cambia_rol_nombre_y_clave(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    ruta = f"/api/plataforma/usuarios/{datos.acme_visualizador.id}"
    respuesta = cliente.patch(ruta, json={"rol": "constructor", "nombre": "Vera Promovida"})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["rol"] == "constructor"
    assert respuesta.json()["nombre"] == "Vera Promovida"

    corta = cliente.post(f"{ruta}/clave", json={"clave": "corta"})
    assert corta.status_code == 400
    assert corta.json()["codigo"] == "E-PLAT-06"
    assert cliente.post(f"{ruta}/clave", json={"clave": "clave-nueva-de-vera"}).status_code == 200

    cliente.post("/api/auth/logout")
    vieja = cliente.post("/api/auth/login", json={"email": "visualizador@acme.test", "clave": CLAVE})
    assert vieja.status_code == 401
    ingresar("visualizador@acme.test", "clave-nueva-de-vera")


def test_admin_modifica_organizacion(cliente, datos, ingresar):
    ingresar("admin@uboard.test")
    ruta = f"/api/plataforma/organizaciones/{datos.acme.id}"
    respuesta = cliente.patch(ruta, json={"nombre": "Acme SA", "activa": False})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["nombre"] == "Acme SA"
    assert respuesta.json()["activa"] is False

    # Nombre repetido con otra organizacion
    repetido = cliente.patch(ruta, json={"nombre": "beta"})
    assert repetido.status_code == 409

    cliente.post("/api/auth/logout")
    bloqueado = cliente.post("/api/auth/login", json={"email": "constructor@acme.test", "clave": CLAVE})
    assert bloqueado.status_code == 401
    assert bloqueado.json()["codigo"] == "E-AUTH-05"
