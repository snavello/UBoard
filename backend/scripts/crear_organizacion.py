"""Altas desde la linea de comando: administradores de plataforma,
organizaciones y sus usuarios. Usa las mismas operaciones que la API.

Uso (desde la raiz del repo, con Postgres levantado y migraciones aplicadas):

  # Primer administrador de plataforma (la clave se pide por teclado si no se pasa)
  .venv/Scripts/python.exe backend/scripts/crear_organizacion.py plataforma --email admin@uboard.local --nombre "Admin"

  # Organizacion con su constructor y su visualizador
  .venv/Scripts/python.exe backend/scripts/crear_organizacion.py organizacion --nombre "Acme" \
      --constructor ana@acme.com "Ana Perez" clave-de-ana-123 \
      --visualizador luis@acme.com "Luis Gomez" clave-de-luis-123

  # Juego completo de demo para desarrollo (idempotente)
  .venv/Scripts/python.exe backend/scripts/crear_organizacion.py demo
"""
import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm import Session  # noqa: E402

from app.catalogo import operaciones  # noqa: E402
from app.catalogo.sesion import nueva_sesion  # noqa: E402
from app.catalogo.tablas import RolUsuario  # noqa: E402
from app.nucleo.errores import ErrorApp  # noqa: E402

DEMO_ADMIN = ("admin@uboard.local", "Admin de plataforma", "uboard-plataforma-demo")
DEMO_ORGANIZACION = "Demo"
DEMO_USUARIOS = [
    (RolUsuario.CONSTRUCTOR, "constructor@demo.local", "Constructora Demo", "demo-constructor-1"),
    (RolUsuario.VISUALIZADOR, "visualizador@demo.local", "Visualizador Demo", "demo-visualizador-1"),
]


def _pedir_clave(clave: str | None, para: str) -> str:
    if clave:
        return clave
    clave = getpass.getpass(f"Clave para {para}: ")
    if clave != getpass.getpass("Repetila: "):
        raise SystemExit("Las claves no coinciden.")
    return clave


def crear_plataforma(sesion: Session, email: str, nombre: str, clave: str | None) -> None:
    usuario = operaciones.crear_usuario(
        sesion, email=email, nombre=nombre, clave=_pedir_clave(clave, email), rol=RolUsuario.PLATAFORMA
    )
    print(f"Administrador de plataforma creado: {usuario.email} (id {usuario.id})")


def crear_organizacion(sesion: Session, nombre: str, constructor: list | None, visualizador: list | None) -> None:
    organizacion = operaciones.crear_organizacion(sesion, nombre)
    workspace = operaciones.workspace_principal(organizacion)
    print(f"Organizacion creada: {organizacion.nombre} (id {organizacion.id}), workspace {workspace.id}")
    for rol, datos in ((RolUsuario.CONSTRUCTOR, constructor), (RolUsuario.VISUALIZADOR, visualizador)):
        if not datos:
            continue
        email, nombre_usuario, clave = datos
        usuario = operaciones.crear_usuario(
            sesion, email=email, nombre=nombre_usuario, clave=clave, rol=rol, organizacion=organizacion
        )
        print(f"  {rol.value}: {usuario.email} (id {usuario.id})")


def crear_demo(sesion: Session) -> None:
    """Datos de desarrollo. Si ya existen, avisa y sigue: se puede correr las
    veces que haga falta."""
    email, nombre, clave = DEMO_ADMIN
    if operaciones.buscar_usuario_por_email(sesion, email) is None:
        operaciones.crear_usuario(sesion, email=email, nombre=nombre, clave=clave, rol=RolUsuario.PLATAFORMA)
        print(f"Administrador de plataforma: {email} / {clave}")
    else:
        print(f"Administrador de plataforma ya existia: {email}")

    try:
        organizacion = operaciones.crear_organizacion(sesion, DEMO_ORGANIZACION)
        print(f"Organizacion {DEMO_ORGANIZACION} creada (id {organizacion.id})")
    except ErrorApp as error:
        if error.codigo != "E-PLAT-01":
            raise
        from sqlalchemy import func, select

        from app.catalogo.tablas import Organizacion

        organizacion = sesion.scalar(
            select(Organizacion).where(func.lower(Organizacion.nombre) == DEMO_ORGANIZACION.lower())
        )
        print(f"Organizacion {DEMO_ORGANIZACION} ya existia (id {organizacion.id})")

    for rol, email, nombre, clave in DEMO_USUARIOS:
        if operaciones.buscar_usuario_por_email(sesion, email) is None:
            operaciones.crear_usuario(sesion, email=email, nombre=nombre, clave=clave, rol=rol, organizacion=organizacion)
            print(f"  {rol.value}: {email} / {clave}")
        else:
            print(f"  {rol.value} ya existia: {email}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Altas de plataforma, organizaciones y usuarios de UBoard.")
    comandos = parser.add_subparsers(dest="comando", required=True)

    plataforma = comandos.add_parser("plataforma", help="crear un administrador de plataforma")
    plataforma.add_argument("--email", required=True)
    plataforma.add_argument("--nombre", required=True)
    plataforma.add_argument("--clave", help="si se omite, se pide por teclado")

    organizacion = comandos.add_parser("organizacion", help="crear una organizacion y, opcionalmente, sus usuarios")
    organizacion.add_argument("--nombre", required=True)
    organizacion.add_argument("--constructor", nargs=3, metavar=("EMAIL", "NOMBRE", "CLAVE"))
    organizacion.add_argument("--visualizador", nargs=3, metavar=("EMAIL", "NOMBRE", "CLAVE"))

    comandos.add_parser("demo", help="juego de datos de desarrollo (admin + organizacion Demo + 2 usuarios)")

    argumentos = parser.parse_args(argv)
    sesion = nueva_sesion()
    try:
        if argumentos.comando == "plataforma":
            crear_plataforma(sesion, argumentos.email, argumentos.nombre, argumentos.clave)
        elif argumentos.comando == "organizacion":
            crear_organizacion(sesion, argumentos.nombre, argumentos.constructor, argumentos.visualizador)
        else:
            crear_demo(sesion)
        sesion.commit()
    except ErrorApp as error:
        sesion.rollback()
        detalle = f" ({error.detalle})" if error.detalle else ""
        print(f"Error {error.codigo}: {error.mensaje}{detalle}", file=sys.stderr)
        return 1
    finally:
        sesion.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
