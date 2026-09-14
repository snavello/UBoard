"""Estructura de un texto sin delimitador estandar, propuesta por Claude
(fase 4, "texto estructurado"). Claude ve una muestra cruda de las primeras
lineas y devuelve una `RecetaTexto` (ancho fijo u regex) que se aplica UNA
sola vez, de forma deterministica, sobre todo el archivo
(app/ingesta/estructura.py) -- Claude nunca parsea fila por fila, ni por
costo ni por consistencia. Mismo patron que inferencia/semantica.py e
inferencia/spec.py: pedido compacto, salida Pydantic, validacion propia,
reintento con feedback, cache por huella en la tabla `inferencia`.
"""
from __future__ import annotations

import json

from app.ingesta.estructura import RecetaTexto, validar_receta
from app.inferencia.llm import ClienteLLM, RespuestaLLM
from app.inferencia.semantica import huella_pedido  # generico: modelo|sistema|pedido, sin nada especifico de semantica
from app.nucleo.errores import ErrorApp

MAX_LINEAS_MUESTRA = 25
MAX_TOKENS_ESTRUCTURA = 3000

SISTEMA = """Sos parte de UBoard, un BI para pymes argentinas. Recibís una muestra de las
primeras líneas crudas de un archivo de texto SIN delimitador estándar (no es
un CSV): puede ser un reporte de ancho fijo (columnas alineadas por posición,
típico de sistemas legacy) o texto con un patrón que se repite en cada línea
pero sin separador consistente. Tu trabajo es proponer cómo partirlo en
columnas.
Reglas:
- Si las columnas están alineadas por POSICIÓN (mismo lugar en cada línea),
  usá modo "ancho_fijo": para cada columna, el nombre y el rango [inicio, fin)
  en caracteres (0-based, fin exclusivo), sin superponerse, cubriendo toda la
  línea.
- Si no hay alineación fija pero SÍ un patrón que se repite, usá modo "regex":
  un patrón Python con un grupo de captura `(...)` por columna, EN EL MISMO
  ORDEN que las columnas que declarás. Preferí grupos simples y robustos
  (dígitos, letras, separadores que veas repetirse) antes que uno que
  dependa de un caso muy puntual de la muestra.
- Nombres de columna cortos, en minúscula, con guion bajo si hace falta (se
  normalizan igual del otro lado, no hace falta que sean perfectos).
- No inventes columnas para separadores, espacios en blanco o relleno sin
  datos reales.
- Si una línea de la muestra parece un título o un total, no cambies la
  receta por eso: proponé la estructura que sirve para la MAYORÍA de las
  líneas."""


def armar_pedido(lineas_muestra: list[str]) -> str:
    return json.dumps({"lineas": lineas_muestra}, ensure_ascii=False, separators=(",", ":"))


def consultar_estructura(cliente: ClienteLLM, lineas_muestra: list[str], pedido: str) -> tuple[RecetaTexto, RespuestaLLM]:
    """Pide, valida contra las lineas de muestra y reintenta UNA vez con los
    errores como feedback. Si la segunda tambien falla, E-INF-06."""
    usuario = pedido
    ultima: RespuestaLLM | None = None
    errores: list[str] = []
    for intento in range(2):
        if intento == 1:
            usuario = (
                pedido
                + "\n\nTu receta anterior tenía estos errores; corregilos y devolvé la receta completa de nuevo:\n- "
                + "\n- ".join(errores)
            )
        ultima = cliente.completar(sistema=SISTEMA, usuario=usuario, esquema=RecetaTexto, max_tokens=MAX_TOKENS_ESTRUCTURA)
        receta = RecetaTexto.model_validate(ultima.contenido)
        errores = validar_receta(lineas_muestra, receta)
        if not errores:
            return receta, ultima
    raise ErrorApp("E-INF-06", "; ".join(errores[:5]))
