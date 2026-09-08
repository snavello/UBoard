"""Login, logout y "quien soy". La sesion viaja en la cookie httpOnly
`sesion_uboard`; el frontend nunca ve el token."""
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.esquemas import UsuarioSalida, a_usuario_salida
from app.catalogo import operaciones
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import Usuario
from app.nucleo import auth
from app.nucleo.errores import ErrorApp

router = APIRouter(prefix="/auth", tags=["auth"])


class Credenciales(BaseModel):
    email: str
    clave: str


@router.post("/login", response_model=UsuarioSalida)
def login(credenciales: Credenciales, response: Response, sesion: Session = Depends(obtener_sesion)) -> UsuarioSalida:
    usuario = operaciones.buscar_usuario_por_email(sesion, credenciales.email)
    # Mismo error para email inexistente y clave incorrecta: no revelar cuales existen
    if usuario is None or not auth.verificar_clave(credenciales.clave, usuario.clave_hash):
        raise ErrorApp("E-AUTH-01")
    auth.verificar_habilitado(usuario)
    operaciones.registrar_acceso(sesion, usuario)
    sesion.commit()
    auth.poner_cookie_sesion(response, auth.crear_token(usuario))
    return a_usuario_salida(usuario)


@router.post("/logout")
def logout(response: Response) -> dict:
    auth.borrar_cookie_sesion(response)
    return {"ok": True}


@router.get("/yo", response_model=UsuarioSalida)
def yo(usuario: Usuario = Depends(auth.usuario_actual)) -> UsuarioSalida:
    return a_usuario_salida(usuario)
