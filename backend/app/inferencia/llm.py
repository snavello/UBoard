"""Cliente de Claude detras de una interfaz. `ClienteAnthropic` usa el SDK
oficial con salida estructurada (`messages.parse` + Pydantic); `ClienteFalso`
devuelve respuestas grabadas para los tests, que nunca tocan la red.

La clave nunca se loguea ni viaja al frontend; las muestras de datos
tampoco se loguean.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
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


class ClienteLLM(ABC):
    @abstractmethod
    def completar(self, *, sistema: str, usuario: str, esquema: type[T], max_tokens: int = 4096) -> RespuestaLLM:
        """Pide una respuesta que cumpla `esquema` (Pydantic). Devuelve el
        dict ya validado por el SDK, o levanta ErrorApp E-INF-01."""


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


class ClienteFalso(ClienteLLM):
    """Devuelve las respuestas en orden y guarda lo que le pidieron, para que
    los tests inspeccionen el prompt."""

    def __init__(self, respuestas: list[dict[str, Any] | Exception] | None = None, modelo: str = "falso"):
        self.respuestas = list(respuestas or [])
        self.pedidos: list[dict[str, Any]] = []
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
