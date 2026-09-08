"""Operaciones sobre organizaciones y usuarios. Las usan la API de plataforma y
los scripts de linea de comando: una sola implementacion de cada regla."""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalogo.tablas import Organizacion, RolUsuario, Usuario, Workspace
from app.nucleo import auth
from app.nucleo.errores import ErrorApp

NOMBRE_WORKSPACE_INICIAL = "Principal"
LARGO_MINIMO_CLAVE = 8


def normalizar_email(email: str) -> str:
    email = (email or "").strip().lower()
    usuario_parte, _, dominio = email.partition("@")
    if not usuario_parte or "." not in dominio or dominio.startswith(".") or dominio.endswith("."):
        raise ErrorApp("E-PLAT-07", f"email recibido: {email!r}")
    return email


def validar_clave(clave: str) -> None:
    if len(clave or "") < LARGO_MINIMO_CLAVE:
        raise ErrorApp("E-PLAT-06")


def crear_organizacion(sesion: Session, nombre: str) -> Organizacion:
    """Crea la organizacion con su workspace inicial. El nombre se compara sin
    distinguir mayusculas para no tener "Acme" y "acme" conviviendo."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorApp("E-PLAT-01", "el nombre esta vacio")
    existente = sesion.scalar(select(Organizacion).where(func.lower(Organizacion.nombre) == nombre.lower()))
    if existente is not None:
        raise ErrorApp("E-PLAT-01", f"nombre: {nombre!r}")
    organizacion = Organizacion(nombre=nombre)
    organizacion.workspaces.append(Workspace(nombre=NOMBRE_WORKSPACE_INICIAL))
    sesion.add(organizacion)
    sesion.flush()
    return organizacion


def obtener_organizacion(sesion: Session, organizacion_id: int) -> Organizacion:
    organizacion = sesion.get(Organizacion, organizacion_id)
    if organizacion is None:
        raise ErrorApp("E-PLAT-03", f"id: {organizacion_id}")
    return organizacion


def obtener_usuario(sesion: Session, usuario_id: int) -> Usuario:
    usuario = sesion.get(Usuario, usuario_id)
    if usuario is None:
        raise ErrorApp("E-PLAT-04", f"id: {usuario_id}")
    return usuario


def buscar_usuario_por_email(sesion: Session, email: str) -> Usuario | None:
    return sesion.scalar(select(Usuario).where(Usuario.email == (email or "").strip().lower()))


def crear_usuario(
    sesion: Session,
    *,
    email: str,
    nombre: str,
    clave: str,
    rol: RolUsuario,
    organizacion: Organizacion | None = None,
) -> Usuario:
    """Alta de usuario. El rol plataforma va sin organizacion; los demas la
    necesitan (la tabla ademas lo exige con un CHECK)."""
    email = normalizar_email(email)
    validar_clave(clave)
    if rol == RolUsuario.PLATAFORMA and organizacion is not None:
        raise ValueError("un usuario de plataforma no pertenece a una organizacion")
    if rol != RolUsuario.PLATAFORMA and organizacion is None:
        raise ValueError(f"un usuario {rol.value} necesita organizacion")
    if buscar_usuario_por_email(sesion, email) is not None:
        raise ErrorApp("E-PLAT-02", f"email: {email}")
    usuario = Usuario(
        email=email,
        nombre=(nombre or "").strip() or email,
        clave_hash=auth.hashear_clave(clave),
        rol=rol,
        organizacion=organizacion,
    )
    sesion.add(usuario)
    sesion.flush()
    return usuario


def cambiar_clave(sesion: Session, usuario: Usuario, clave_nueva: str) -> None:
    validar_clave(clave_nueva)
    usuario.clave_hash = auth.hashear_clave(clave_nueva)
    sesion.flush()


def cambiar_activo(sesion: Session, usuario: Usuario, activo: bool, quien: Usuario) -> None:
    """Activa o desactiva. Nadie se desactiva a si mismo, y siempre queda al
    menos un administrador de plataforma activo."""
    if not activo and usuario.id == quien.id:
        raise ErrorApp("E-PLAT-08")
    if not activo and usuario.rol == RolUsuario.PLATAFORMA and usuario.activo:
        activos = sesion.scalar(
            select(func.count()).select_from(Usuario).where(Usuario.rol == RolUsuario.PLATAFORMA, Usuario.activo.is_(True))
        )
        if activos <= 1:
            raise ErrorApp("E-PLAT-05")
    usuario.activo = activo
    sesion.flush()


def registrar_acceso(sesion: Session, usuario: Usuario) -> None:
    usuario.ultimo_acceso = datetime.now(timezone.utc)
    sesion.flush()


def workspace_principal(organizacion: Organizacion | None) -> Workspace | None:
    """En v1 cada organizacion tiene un solo workspace; este helper es el unico
    lugar que asume eso."""
    if organizacion is None or not organizacion.workspaces:
        return None
    return organizacion.workspaces[0]
