"""Autenticacion: claves hasheadas, sesion como JWT en cookie httpOnly.

- Claves: PBKDF2-HMAC-SHA256 con sal por usuario, de la biblioteca estandar
  (mismo esquema que Mi Trabajo; sin dependencias extra).
- Sesion: JWT firmado (HS256) guardado en la cookie `sesion_uboard`. Vence por
  INACTIVIDAD: cada request autenticado reemite la cookie con vencimiento
  nuevo (renovacion deslizante en `usuario_actual`), asi que un usuario activo
  nunca se desloguea solo.
- Roles: `exigir_rol(...)` arma la dependencia que usan los routers. El
  visualizador no tiene rutas de escritura porque esas rutas exigen
  constructor; no es un if dentro del handler.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import RolUsuario, Usuario
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp

NOMBRE_COOKIE = "sesion_uboard"
ALGORITMO_JWT = "HS256"
ITERACIONES_PBKDF2 = 100_000


# ---------- Claves ----------
def hashear_clave(clave: str) -> str:
    """Devuelve 'sal$hash'."""
    sal = secrets.token_hex(16)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), ITERACIONES_PBKDF2)
    return f"{sal}${derivada.hex()}"


def verificar_clave(clave: str, clave_hash: str) -> bool:
    if not clave_hash or "$" not in clave_hash:
        return False
    sal, guardado = clave_hash.split("$", 1)
    derivada = hashlib.pbkdf2_hmac("sha256", clave.encode(), sal.encode(), ITERACIONES_PBKDF2)
    return hmac.compare_digest(derivada.hex(), guardado)


# ---------- Tokens ----------
def crear_token(usuario: Usuario, ahora: datetime | None = None) -> str:
    """JWT con el minimo necesario: quien es (sub), que rol tiene y de que
    organizacion. `ahora` se puede fijar en tests para fabricar tokens vencidos."""
    configuracion = obtener_configuracion()
    ahora = ahora or datetime.now(timezone.utc)
    carga = {
        "sub": str(usuario.id),
        "rol": usuario.rol.value,
        "org": usuario.organizacion_id,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=configuracion.minutos_inactividad),
    }
    return jwt.encode(carga, configuracion.secreto_sesion, algorithm=ALGORITMO_JWT)


def leer_token(token: str) -> dict | None:
    """Valida firma y vencimiento. Devuelve la carga o None si no sirve."""
    configuracion = obtener_configuracion()
    try:
        return jwt.decode(
            token,
            configuracion.secreto_sesion,
            algorithms=[ALGORITMO_JWT],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None


# ---------- Cookie ----------
def poner_cookie_sesion(response: Response, token: str) -> None:
    configuracion = obtener_configuracion()
    response.set_cookie(
        key=NOMBRE_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        # En local se navega por http; en cualquier otro entorno la cookie solo viaja por https
        secure=configuracion.entorno != "local",
        max_age=configuracion.minutos_inactividad * 60,
        path="/",
    )


def borrar_cookie_sesion(response: Response) -> None:
    response.delete_cookie(NOMBRE_COOKIE, path="/")


# ---------- Dependencias ----------
def verificar_habilitado(usuario: Usuario) -> None:
    """Un usuario desactivado, o de una organizacion desactivada, no entra."""
    if not usuario.activo:
        raise ErrorApp("E-AUTH-04")
    if usuario.organizacion is not None and not usuario.organizacion.activa:
        raise ErrorApp("E-AUTH-05")


def usuario_actual(
    request: Request,
    response: Response,
    sesion: Session = Depends(obtener_sesion),
) -> Usuario:
    """Lee la cookie, valida el token, carga el usuario y renueva la cookie
    (renovacion deslizante). El `response` es el de la respuesta final: FastAPI
    fusiona las cookies que se setean en una dependencia."""
    token = request.cookies.get(NOMBRE_COOKIE)
    carga = leer_token(token) if token else None
    if carga is None:
        raise ErrorApp("E-AUTH-02")
    usuario = sesion.get(Usuario, int(carga["sub"]))
    if usuario is None:
        raise ErrorApp("E-AUTH-02")
    verificar_habilitado(usuario)
    poner_cookie_sesion(response, crear_token(usuario))
    return usuario


def exigir_rol(*roles: RolUsuario):
    """Dependencia que exige uno de los roles dados. Usar a nivel de router
    (`dependencies=[Depends(exigir_rol(RolUsuario.CONSTRUCTOR))]`) para que
    toda la familia de rutas quede protegida de una."""

    def dependencia(usuario: Usuario = Depends(usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise ErrorApp("E-AUTH-03")
        return usuario

    return dependencia
