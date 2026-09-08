"""FastAPI sirve el build de Vite: index.html para cualquier ruta que no sea
de la API (el router de React resuelve), y 404 real para /api desconocidas."""
import pytest
from fastapi.testclient import TestClient

from app.main import RUTA_ESTATICO, app

hay_build = (RUTA_ESTATICO / "index.html").exists()


@pytest.mark.skipif(not hay_build, reason="no hay build del frontend (npm run build)")
def test_raiz_devuelve_index_html():
    cliente = TestClient(app)
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "text/html" in respuesta.headers["content-type"]
    assert 'id="raiz"' in respuesta.text


@pytest.mark.skipif(not hay_build, reason="no hay build del frontend (npm run build)")
def test_ruta_del_router_de_react_tambien_devuelve_index_html():
    cliente = TestClient(app)
    respuesta = cliente.get("/tablero/cualquier-cosa")
    assert respuesta.status_code == 200
    assert 'id="raiz"' in respuesta.text
    assert respuesta.headers["cache-control"] == "no-cache"
