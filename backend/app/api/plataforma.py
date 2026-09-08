"""Administracion de plataforma: organizaciones y usuarios. Solo rol
`plataforma`; el router entero exige el rol, no cada ruta."""
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.esquemas import UsuarioSalida, a_usuario_salida
from app.catalogo import operaciones
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import Organizacion, RolUsuario, Usuario
from app.nucleo.auth import exigir_rol
from app.nucleo.errores import ErrorApp

router = APIRouter(
    prefix="/plataforma",
    tags=["plataforma"],
    dependencies=[Depends(exigir_rol(RolUsuario.PLATAFORMA))],
)


# ---------- Esquemas ----------
class OrganizacionSalida(BaseModel):
    id: int
    nombre: str
    activa: bool
    workspace_id: int | None
    cantidad_usuarios: int


class OrganizacionEntrada(BaseModel):
    nombre: str


class OrganizacionCambios(BaseModel):
    nombre: str | None = None
    activa: bool | None = None


class UsuarioOrganizacionEntrada(BaseModel):
    email: str
    nombre: str
    clave: str
    # El rol plataforma no se crea por aca: tiene su propia ruta
    rol: Literal["constructor", "visualizador"]


class AdministradorEntrada(BaseModel):
    email: str
    nombre: str
    clave: str


class UsuarioCambios(BaseModel):
    nombre: str | None = None
    activo: bool | None = None
    rol: Literal["constructor", "visualizador"] | None = None


class ClaveNueva(BaseModel):
    clave: str


def _a_organizacion_salida(sesion: Session, organizacion: Organizacion) -> OrganizacionSalida:
    cantidad = sesion.scalar(select(func.count()).select_from(Usuario).where(Usuario.organizacion_id == organizacion.id))
    workspace = operaciones.workspace_principal(organizacion)
    return OrganizacionSalida(
        id=organizacion.id,
        nombre=organizacion.nombre,
        activa=organizacion.activa,
        workspace_id=workspace.id if workspace else None,
        cantidad_usuarios=cantidad or 0,
    )


# ---------- Organizaciones ----------
@router.get("/organizaciones", response_model=list[OrganizacionSalida])
def listar_organizaciones(sesion: Session = Depends(obtener_sesion)) -> list[OrganizacionSalida]:
    organizaciones = sesion.scalars(select(Organizacion).order_by(Organizacion.nombre)).all()
    return [_a_organizacion_salida(sesion, organizacion) for organizacion in organizaciones]


@router.post("/organizaciones", response_model=OrganizacionSalida, status_code=status.HTTP_201_CREATED)
def crear_organizacion(entrada: OrganizacionEntrada, sesion: Session = Depends(obtener_sesion)) -> OrganizacionSalida:
    organizacion = operaciones.crear_organizacion(sesion, entrada.nombre)
    sesion.commit()
    return _a_organizacion_salida(sesion, organizacion)


@router.patch("/organizaciones/{organizacion_id}", response_model=OrganizacionSalida)
def modificar_organizacion(
    organizacion_id: int, cambios: OrganizacionCambios, sesion: Session = Depends(obtener_sesion)
) -> OrganizacionSalida:
    organizacion = operaciones.obtener_organizacion(sesion, organizacion_id)
    if cambios.nombre is not None and cambios.nombre.strip() != organizacion.nombre:
        nombre = cambios.nombre.strip()
        repetida = sesion.scalar(
            select(Organizacion).where(func.lower(Organizacion.nombre) == nombre.lower(), Organizacion.id != organizacion.id)
        )
        if repetida is not None or not nombre:
            raise ErrorApp("E-PLAT-01", f"nombre: {nombre!r}")
        organizacion.nombre = nombre
    if cambios.activa is not None:
        organizacion.activa = cambios.activa
    sesion.commit()
    return _a_organizacion_salida(sesion, organizacion)


# ---------- Usuarios de una organizacion ----------
@router.get("/organizaciones/{organizacion_id}/usuarios", response_model=list[UsuarioSalida])
def listar_usuarios(organizacion_id: int, sesion: Session = Depends(obtener_sesion)) -> list[UsuarioSalida]:
    organizacion = operaciones.obtener_organizacion(sesion, organizacion_id)
    return [a_usuario_salida(usuario) for usuario in organizacion.usuarios]


@router.post(
    "/organizaciones/{organizacion_id}/usuarios",
    response_model=UsuarioSalida,
    status_code=status.HTTP_201_CREATED,
)
def crear_usuario(
    organizacion_id: int, entrada: UsuarioOrganizacionEntrada, sesion: Session = Depends(obtener_sesion)
) -> UsuarioSalida:
    organizacion = operaciones.obtener_organizacion(sesion, organizacion_id)
    usuario = operaciones.crear_usuario(
        sesion,
        email=entrada.email,
        nombre=entrada.nombre,
        clave=entrada.clave,
        rol=RolUsuario(entrada.rol),
        organizacion=organizacion,
    )
    sesion.commit()
    return a_usuario_salida(usuario)


# ---------- Administradores de plataforma ----------
@router.get("/administradores", response_model=list[UsuarioSalida])
def listar_administradores(sesion: Session = Depends(obtener_sesion)) -> list[UsuarioSalida]:
    administradores = sesion.scalars(
        select(Usuario).where(Usuario.rol == RolUsuario.PLATAFORMA).order_by(Usuario.id)
    ).all()
    return [a_usuario_salida(usuario) for usuario in administradores]


@router.post("/administradores", response_model=UsuarioSalida, status_code=status.HTTP_201_CREATED)
def crear_administrador(entrada: AdministradorEntrada, sesion: Session = Depends(obtener_sesion)) -> UsuarioSalida:
    usuario = operaciones.crear_usuario(
        sesion, email=entrada.email, nombre=entrada.nombre, clave=entrada.clave, rol=RolUsuario.PLATAFORMA
    )
    sesion.commit()
    return a_usuario_salida(usuario)


# ---------- Cualquier usuario ----------
@router.patch("/usuarios/{usuario_id}", response_model=UsuarioSalida)
def modificar_usuario(
    usuario_id: int,
    cambios: UsuarioCambios,
    quien: Usuario = Depends(exigir_rol(RolUsuario.PLATAFORMA)),
    sesion: Session = Depends(obtener_sesion),
) -> UsuarioSalida:
    usuario = operaciones.obtener_usuario(sesion, usuario_id)
    if cambios.nombre is not None and cambios.nombre.strip():
        usuario.nombre = cambios.nombre.strip()
    if cambios.rol is not None:
        if usuario.rol == RolUsuario.PLATAFORMA:
            raise ErrorApp("E-AUTH-03", "un administrador de plataforma no cambia de rol")
        usuario.rol = RolUsuario(cambios.rol)
    if cambios.activo is not None:
        operaciones.cambiar_activo(sesion, usuario, cambios.activo, quien)
    sesion.commit()
    return a_usuario_salida(usuario)


@router.post("/usuarios/{usuario_id}/clave", response_model=UsuarioSalida)
def restablecer_clave(usuario_id: int, entrada: ClaveNueva, sesion: Session = Depends(obtener_sesion)) -> UsuarioSalida:
    usuario = operaciones.obtener_usuario(sesion, usuario_id)
    operaciones.cambiar_clave(sesion, usuario, entrada.clave)
    sesion.commit()
    return a_usuario_salida(usuario)
