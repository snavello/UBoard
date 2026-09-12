"""Cliente de Claude detras de una interfaz. `ClienteAnthropic` usa el SDK
oficial: `completar` para salida estructurada de un solo turno
(`messages.parse` + Pydantic, fase 2) y `conversar` para tool-use
multi-turno (`messages.create` con `tools`, fase 3, paso 19). `ClienteFalso`
devuelve respuestas grabadas para los tests, que nunca tocan la red.

La clave nunca se loguea ni viaja al frontend; las muestras de datos
tampoco se loguean.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp

registro = logging.getLogger("uboard.llm")

T = TypeVar("T", bound=BaseModel)


@dataclass
class RespuestaLLM:
    contenido: dict[str, Any]
    modelo: str
    tokens_entrada: int
    tokens_salida: int


@dataclass
class LlamadaHerramienta:
    id: str
    nombre: str
    entrada: dict[str, Any]


@dataclass
class RespuestaConversacion:
    """Un turno de `conversar`. `bloques` es el `content` crudo (como dict,
    listo para JSON) que hay que reenviar tal cual en el mensaje `assistant`
    del turno siguiente. `es_final` = True cuando Claude ya no pide mas
    herramientas (stop_reason distinto de tool_use): ahi `texto` es la
    respuesta para la persona."""

    bloques: list[dict[str, Any]]
    llamadas: list[LlamadaHerramienta] = field(default_factory=list)
    texto: str = ""
    es_final: bool = True
    tokens_entrada: int = 0
    tokens_salida: int = 0


class ClienteLLM(ABC):
    @abstractmethod
    def completar(self, *, sistema: str, usuario: str, esquema: type[T], max_tokens: int = 4096) -> RespuestaLLM:
        """Pide una respuesta que cumpla `esquema` (Pydantic). Devuelve el
        dict ya validado por el SDK, o levanta ErrorApp E-INF-01."""

    @abstractmethod
    def conversar(
        self, *, sistema: str, mensajes: list[dict[str, Any]], herramientas: list[dict[str, Any]], max_tokens: int = 2048
    ) -> RespuestaConversacion:
        """Un turno de tool-use: `mensajes` y `herramientas` ya en el formato
        de la API de Anthropic. El llamador arma el loop (motor.py); esta
        funcion solo hace UN pedido y traduce la respuesta. ErrorApp E-ASI-01
        si Claude no responde."""


class ClienteAnthropic(ClienteLLM):
    def __init__(self, api_key: str, modelo: str, timeout_segundos: float = 120.0):
        import anthropic

        self._anthropic = anthropic
        self._cliente = anthropic.Anthropic(api_key=api_key, timeout=timeout_segundos, max_retries=2)
        self.modelo = modelo

    def completar(self, *, sistema: str, usuario: str, esquema: type[T], max_tokens: int = 4096) -> RespuestaLLM:
        try:
            respuesta = self._cliente.messages.parse(
                model=self.modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": usuario}],
                output_format=esquema,
            )
        except self._anthropic.APIError as error:
            registro.warning("Claude fallo: %s", error)
            raise ErrorApp("E-INF-01", f"{type(error).__name__}: {getattr(error, 'message', str(error))[:200]}") from error
        if respuesta.parsed_output is None:
            raise ErrorApp("E-INF-01", f"sin salida estructurada (stop_reason={respuesta.stop_reason})")
        return RespuestaLLM(
            contenido=respuesta.parsed_output.model_dump(mode="json"),
            modelo=respuesta.model,
            tokens_entrada=respuesta.usage.input_tokens,
            tokens_salida=respuesta.usage.output_tokens,
        )

    def conversar(
        self, *, sistema: str, mensajes: list[dict[str, Any]], herramientas: list[dict[str, Any]], max_tokens: int = 2048
    ) -> RespuestaConversacion:
        try:
            respuesta = self._cliente.messages.create(
                model=self.modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=mensajes,
                tools=herramientas,
            )
        except self._anthropic.APIError as error:
            registro.warning("Claude fallo (chat): %s", error)
            raise ErrorApp("E-ASI-01", f"{type(error).__name__}: {getattr(error, 'message', str(error))[:200]}") from error
        bloques = [bloque.model_dump() for bloque in respuesta.content]
        llamadas = [
            LlamadaHerramienta(id=bloque["id"], nombre=bloque["name"], entrada=bloque["input"])
            for bloque in bloques
            if bloque["type"] == "tool_use"
        ]
        texto = "".join(bloque["text"] for bloque in bloques if bloque["type"] == "text")
        return RespuestaConversacion(
            bloques=bloques,
            llamadas=llamadas,
            texto=texto,
            es_final=respuesta.stop_reason != "tool_use",
            tokens_entrada=respuesta.usage.input_tokens,
            tokens_salida=respuesta.usage.output_tokens,
        )


RespuestaChatFalsa = str | list[tuple[str, dict[str, Any]]] | Exception


class ClienteFalso(ClienteLLM):
    """Devuelve las respuestas en orden y guarda lo que le pidieron, para que
    los tests inspeccionen el prompt.

    `respuestas_chat` (para `conversar`) es una lista de: un string (Claude
    responde con ese texto, turno final) o una lista de `(nombre_herramienta,
    entrada)` (Claude pide esas herramientas en un solo turno, una por cada
    una); un `Exception` se levanta tal cual, para probar errores."""

    def __init__(
        self,
        respuestas: list[dict[str, Any] | Exception] | None = None,
        respuestas_chat: list[RespuestaChatFalsa] | None = None,
        modelo: str = "falso",
    ):
        self.respuestas = list(respuestas or [])
        self.respuestas_chat = list(respuestas_chat or [])
        self.pedidos: list[dict[str, Any]] = []
        self.turnos_chat: list[list[dict[str, Any]]] = []
        self.modelo = modelo

    def completar(self, *, sistema: str, usuario: str, esquema: type[T], max_tokens: int = 4096) -> RespuestaLLM:
        self.pedidos.append({"sistema": sistema, "usuario": usuario, "esquema": esquema.__name__})
        if not self.respuestas:
            raise ErrorApp("E-INF-01", "el cliente falso se quedo sin respuestas")
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        contenido = esquema.model_validate(siguiente).model_dump(mode="json")
        return RespuestaLLM(contenido=contenido, modelo=self.modelo, tokens_entrada=100, tokens_salida=50)

    def conversar(
        self, *, sistema: str, mensajes: list[dict[str, Any]], herramientas: list[dict[str, Any]], max_tokens: int = 2048
    ) -> RespuestaConversacion:
        self.turnos_chat.append(mensajes)
        if not self.respuestas_chat:
            raise ErrorApp("E-ASI-01", "el cliente falso se quedo sin respuestas de chat")
        siguiente = self.respuestas_chat.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        if isinstance(siguiente, str):
            return RespuestaConversacion(
                bloques=[{"type": "text", "text": siguiente}], texto=siguiente, es_final=True, tokens_entrada=50, tokens_salida=20
            )
        llamadas = [LlamadaHerramienta(id=f"llamada_falsa_{indice}", nombre=nombre, entrada=entrada) for indice, (nombre, entrada) in enumerate(siguiente)]
        bloques = [{"type": "tool_use", "id": llamada.id, "name": llamada.nombre, "input": llamada.entrada} for llamada in llamadas]
        return RespuestaConversacion(bloques=bloques, llamadas=llamadas, texto="", es_final=False, tokens_entrada=80, tokens_salida=30)


_reemplazo: ClienteLLM | None = None


def fijar_cliente_llm(cliente: ClienteLLM | None) -> None:
    """Para tests: reemplaza el cliente real (None vuelve al de la config)."""
    global _reemplazo
    _reemplazo = cliente


def obtener_cliente_llm() -> ClienteLLM | None:
    """None cuando no hay clave configurada: la inferencia sigue solo con
    heuristicas y avisa."""
    if _reemplazo is not None:
        return _reemplazo
    configuracion = obtener_configuracion()
    if not configuracion.anthropic_api_key:
        return None
    return ClienteAnthropic(configuracion.anthropic_api_key, configuracion.modelo_claude, configuracion.timeout_llm_segundos)
