"""Esquemas Pydantic compartidos por varios routers (salidas de usuario,
organizacion y workspace)."""
from datetime import datetime

from pydantic import BaseModel

from app.catalogo.operaciones import workspace_principal
from app.catalogo.tablas import Organizacion, RolUsuario, Usuario, Workspace


class OrganizacionResumen(BaseModel):
    id: int
    nombre: str
    activa: bool


class WorkspaceSalida(BaseModel):
    id: int
    organizacion_id: int
    nombre: str
    creado_en: datetime


class UsuarioSalida(BaseModel):
    id: int
    email: str
    nombre: str
    rol: RolUsuario
    activo: bool
    organizacion: OrganizacionResumen | None
    # Workspace unico de la organizacion en v1; None para plataforma
    workspace_id: int | None
    ultimo_acceso: datetime | None


def a_organizacion_resumen(organizacion: Organizacion) -> OrganizacionResumen:
    return OrganizacionResumen(id=organizacion.id, nombre=organizacion.nombre, activa=organizacion.activa)


def a_workspace_salida(workspace: Workspace) -> WorkspaceSalida:
    return WorkspaceSalida(
        id=workspace.id,
        organizacion_id=workspace.organizacion_id,
        nombre=workspace.nombre,
        creado_en=workspace.creado_en,
    )


def a_usuario_salida(usuario: Usuario) -> UsuarioSalida:
    organizacion = usuario.organizacion
    workspace = workspace_principal(organizacion)
    return UsuarioSalida(
        id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        rol=usuario.rol,
        activo=usuario.activo,
        organizacion=a_organizacion_resumen(organizacion) if organizacion else None,
        workspace_id=workspace.id if workspace else None,
        ultimo_acceso=usuario.ultimo_acceso,
    )
