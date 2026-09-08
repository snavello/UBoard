"""Errores con codigo propio.

Todo error que ve una persona lleva un codigo (`raise ErrorApp("E-AUTH-01")`):
el frontend muestra el mensaje y el codigo, y con el codigo se encuentra el
lugar exacto en el backend. E-INTERNO-00 es el unico que admite no saber que
paso; por eso lleva un `ref` que se imprime junto al traceback en el log.
"""
import logging
import secrets
import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

registro = logging.getLogger("uboard")

# codigo -> (estado HTTP, mensaje para la persona)
MENSAJES: dict[str, tuple[int, str]] = {
    "E-AUTH-01": (401, "Email o clave incorrectos."),
    "E-AUTH-02": (401, "Tu sesión venció o no iniciaste sesión. Volvé a ingresar."),
    "E-AUTH-03": (403, "No tenés permiso para hacer esto."),
    "E-AUTH-04": (401, "Tu usuario está desactivado. Hablá con quien administra la plataforma."),
    "E-AUTH-05": (401, "La organización está desactivada."),
    "E-PLAT-01": (409, "Ya existe una organización con ese nombre."),
    "E-PLAT-02": (409, "Ya hay un usuario con ese email."),
    "E-PLAT-03": (404, "No encontramos esa organización."),
    "E-PLAT-04": (404, "No encontramos ese usuario."),
    "E-PLAT-05": (400, "No podés desactivar al último administrador de plataforma activo."),
    "E-PLAT-06": (400, "La clave tiene que tener al menos 8 caracteres."),
    "E-PLAT-07": (400, "El email no parece válido."),
    "E-PLAT-08": (400, "No podés desactivar tu propio usuario."),
    "E-WS-01": (404, "No encontramos ese workspace."),
    "E-INTERNO-00": (500, "Algo salió mal de nuestro lado. Probá de nuevo en un momento."),
}


class ErrorApp(Exception):
    """Error esperado, con codigo del catalogo. `detalle` es opcional y tecnico
    (que campo, que valor); el mensaje para la persona sale de MENSAJES."""

    def __init__(self, codigo: str, detalle: str | None = None):
        if codigo not in MENSAJES:
            raise ValueError(f"Codigo de error desconocido: {codigo}")
        self.codigo = codigo
        self.detalle = detalle
        self.estado, self.mensaje = MENSAJES[codigo]
        super().__init__(f"{codigo}: {self.mensaje}")

    def cuerpo(self) -> dict:
        cuerpo = {"codigo": self.codigo, "mensaje": self.mensaje}
        if self.detalle:
            cuerpo["detalle"] = self.detalle
        return cuerpo


def registrar_manejadores(app: FastAPI) -> None:
    @app.exception_handler(ErrorApp)
    async def _error_app(_: Request, error: ErrorApp) -> JSONResponse:
        return JSONResponse(status_code=error.estado, content=error.cuerpo())

    @app.exception_handler(Exception)
    async def _error_no_manejado(request: Request, error: Exception) -> JSONResponse:
        ref = secrets.token_hex(4)
        registro.error(
            "E-INTERNO-00 ref=%s %s %s\n%s",
            ref,
            request.method,
            request.url.path,
            "".join(traceback.format_exception(error)),
        )
        estado, mensaje = MENSAJES["E-INTERNO-00"]
        return JSONResponse(status_code=estado, content={"codigo": "E-INTERNO-00", "mensaje": mensaje, "ref": ref})
