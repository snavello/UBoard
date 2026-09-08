"""El backend levanta y responde /api/salud con version y entorno."""
from fastapi.testclient import TestClient

from app.main import app
from app.version import VERSION


def test_salud_responde_version_y_entorno():
    cliente = TestClient(app)
    respuesta = cliente.get("/api/salud")
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "ok"
    assert cuerpo["version"] == VERSION
    assert cuerpo["entorno"] in ("local", "pruebas", "demo", "prod")


def test_ruta_de_api_inexistente_no_devuelve_el_frontend():
    cliente = TestClient(app)
    respuesta = cliente.get("/api/no-existe")
    assert respuesta.status_code == 404
