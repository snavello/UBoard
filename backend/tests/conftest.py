"""Fixtures compartidas.

Los tests de API corren contra la base `uboard_test` (DATABASE_URL_TEST) del
mismo Postgres de Docker: mismo motor que produccion, nunca SQLite. Al
empezar la sesion de tests se hace `alembic downgrade base` + `upgrade head`
(asi las migraciones se prueban reversibles en cada corrida) y antes de cada
test se truncan todas las tablas.
"""
import os
from dataclasses import dataclass
from pathlib import Path

# Antes de importar la app: los tests siempre corren como entorno local
# (cookies sin `secure`, sin exigir SECRETO_SESION real) y sin tocar la base
# de trabajo al arrancar (la recuperacion de tareas huerfanas se prueba aparte).
os.environ.setdefault("ENTORNO", "local")
os.environ.setdefault("RECUPERAR_TAREAS_AL_ARRANCAR", "false")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

import app.catalogo.tablas  # noqa: E402, F401  registra las tablas en Base.metadata
from app.almacen import AlmacenLocal, obtener_almacen  # noqa: E402
from app.catalogo import operaciones  # noqa: E402
from app.catalogo.base import Base  # noqa: E402
from app.catalogo.sesion import obtener_sesion  # noqa: E402
from app.catalogo.tablas import Organizacion, RolUsuario, Usuario  # noqa: E402
from app.main import app  # noqa: E402
from app.nucleo.config import obtener_configuracion  # noqa: E402
from app.tareas import ColaLocal, obtener_cola  # noqa: E402

RAIZ_BACKEND = Path(__file__).resolve().parents[1]
CLAVE = "clave-de-prueba-123"


@pytest.fixture(scope="session")
def engine_test():
    configuracion = obtener_configuracion()
    if configuracion.database_url_test == configuracion.database_url:
        pytest.fail("DATABASE_URL_TEST apunta a la misma base que DATABASE_URL: los tests borrarian datos de trabajo")
    engine = create_engine(configuracion.database_url_test)
    try:
        with engine.connect():
            pass
    except OperationalError as error:
        pytest.fail(f"No hay Postgres de tests. Levantalo con `docker compose up -d postgres`. Detalle: {error}")

    os.environ["ALEMBIC_DATABASE_URL"] = configuracion.database_url_test
    config_alembic = Config(str(RAIZ_BACKEND / "alembic.ini"))
    command.downgrade(config_alembic, "base")
    command.upgrade(config_alembic, "head")
    try:
        yield engine
    finally:
        engine.dispose()
        os.environ.pop("ALEMBIC_DATABASE_URL", None)


@pytest.fixture(scope="session")
def fabrica_test(engine_test) -> sessionmaker[Session]:
    return sessionmaker(bind=engine_test, autoflush=False, expire_on_commit=False)


@pytest.fixture
def sesion_db(engine_test, fabrica_test) -> Session:
    """Sesion directa a la base de tests, con las tablas vacias."""
    with engine_test.begin() as conexion:
        tablas = ", ".join(f'"{tabla.name}"' for tabla in Base.metadata.sorted_tables)
        conexion.execute(text(f"TRUNCATE {tablas} RESTART IDENTITY CASCADE"))
    sesion = fabrica_test()
    try:
        yield sesion
    finally:
        sesion.close()


@pytest.fixture
def cliente(fabrica_test, sesion_db) -> TestClient:
    """Cliente HTTP contra la app, con la dependencia de sesion apuntando a la
    base de tests. Guarda cookies entre requests, como un navegador."""

    def _sesion_de_test():
        sesion = fabrica_test()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[obtener_sesion] = _sesion_de_test
    try:
        with TestClient(app) as cliente_http:
            yield cliente_http
    finally:
        app.dependency_overrides.pop(obtener_sesion, None)


@pytest.fixture
def cola(fabrica_test) -> ColaLocal:
    """Cola local con sesiones de la base de tests, inyectada en la app.
    `cola.esperar(id)` bloquea hasta que la tarea termina."""
    cola_local = ColaLocal(fabrica_sesiones=fabrica_test, hilos=1)
    app.dependency_overrides[obtener_cola] = lambda: cola_local
    try:
        yield cola_local
    finally:
        cola_local.cerrar()
        app.dependency_overrides.pop(obtener_cola, None)


@pytest.fixture
def almacen_temporal(tmp_path) -> AlmacenLocal:
    """Almacen en un directorio temporal, inyectado en la app."""
    almacen = AlmacenLocal(tmp_path / "almacen")
    app.dependency_overrides[obtener_almacen] = lambda: almacen
    try:
        yield almacen
    finally:
        app.dependency_overrides.pop(obtener_almacen, None)


@dataclass
class DatosBase:
    admin: Usuario
    acme: Organizacion
    acme_constructor: Usuario
    acme_visualizador: Usuario
    beta: Organizacion
    beta_constructor: Usuario

    @property
    def acme_workspace_id(self) -> int:
        return self.acme.workspaces[0].id

    @property
    def beta_workspace_id(self) -> int:
        return self.beta.workspaces[0].id


@pytest.fixture
def datos(sesion_db) -> DatosBase:
    """Un admin de plataforma y dos organizaciones con usuarios, todos con la
    misma clave CLAVE."""
    admin = operaciones.crear_usuario(
        sesion_db, email="admin@uboard.test", nombre="Admin", clave=CLAVE, rol=RolUsuario.PLATAFORMA
    )
    acme = operaciones.crear_organizacion(sesion_db, "Acme")
    acme_constructor = operaciones.crear_usuario(
        sesion_db, email="constructor@acme.test", nombre="Ana", clave=CLAVE, rol=RolUsuario.CONSTRUCTOR, organizacion=acme
    )
    acme_visualizador = operaciones.crear_usuario(
        sesion_db, email="visualizador@acme.test", nombre="Vera", clave=CLAVE, rol=RolUsuario.VISUALIZADOR, organizacion=acme
    )
    beta = operaciones.crear_organizacion(sesion_db, "Beta")
    beta_constructor = operaciones.crear_usuario(
        sesion_db, email="constructor@beta.test", nombre="Bruno", clave=CLAVE, rol=RolUsuario.CONSTRUCTOR, organizacion=beta
    )
    sesion_db.commit()
    return DatosBase(admin, acme, acme_constructor, acme_visualizador, beta, beta_constructor)


@pytest.fixture
def ingresar(cliente):
    """Hace login y deja la cookie en el cliente. Devuelve la respuesta."""

    def _ingresar(email: str, clave: str = CLAVE):
        respuesta = cliente.post("/api/auth/login", json={"email": email, "clave": clave})
        assert respuesta.status_code == 200, respuesta.text
        return respuesta

    return _ingresar
