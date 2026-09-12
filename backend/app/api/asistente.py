"""API del asistente (fase 3, paso 19): un chat con Claude, con distinto
catalogo de herramientas segun el rol de quien pregunta (constructor:
lectura y escritura; visualizador: solo lectura). Un solo endpoint, un solo
motor (`app/asistente/motor.py`); el historial de la conversacion no se
persiste (cada accion real ya queda como version, eso alcanza)."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.almacen import obtener_almacen
from app.almacen.base import AlmacenArchivos
from app.api.workspaces import workspace_del_usuario
from app.asistente import motor
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import RolUsuario, Usuario, Workspace
from app.inferencia.llm import obtener_cliente_llm
from app.nucleo.auth import exigir_rol
from app.nucleo.errores import ErrorApp

router = APIRouter(prefix="/workspaces/{workspace_id}/asistente", tags=["asistente"])


class MensajeEntrada(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)


class AccionSalida(BaseModel):
    herramienta: str
    resultado: str


class RespuestaSalida(BaseModel):
    texto: str
    acciones: list[AccionSalida]


@router.post("/mensajes", response_model=RespuestaSalida)
def enviar_mensaje(
    entrada: MensajeEntrada,
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR, RolUsuario.VISUALIZADOR)),
    sesion: Session = Depends(obtener_sesion),
    almacen: AlmacenArchivos = Depends(obtener_almacen),
) -> RespuestaSalida:
    """Un pedido del chat. El constructor puede pedir cambios sobre el
    modelo o el dashboard (crea versiones nuevas, como el wizard); el
    visualizador solo puede preguntar sobre los datos. E-ASI-04 sin clave de
    Claude configurada."""
    cliente = obtener_cliente_llm()
    if cliente is None:
        raise ErrorApp("E-ASI-04")
    contexto = motor.armar_contexto(sesion, workspace)
    respuesta = motor.conversar(
        cliente, usuario=usuario, sesion=sesion, workspace=workspace, almacen=almacen, mensaje=entrada.mensaje, contexto=contexto
    )
    return RespuestaSalida(texto=respuesta.texto, acciones=[AccionSalida(herramienta=accion.herramienta, resultado=accion.resultado) for accion in respuesta.acciones])
