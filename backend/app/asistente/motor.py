"""Motor del asistente (fase 3, paso 19): un chat con Claude que puede
ejecutar operaciones granulares (constructor) o solo consultar datos
(visualizador). No persiste la conversacion (decidido en la fase 3, duda 3
de `docs/fase3-lectura-y-plan.md`): lo unico que queda es lo que cada
herramienta deja en la base (una version nueva, igual que si lo hubiera
hecho el wizard).

Loop de tool-use: se manda el pedido, si Claude quiere una o mas
herramientas se ejecutan y se le devuelve el resultado, hasta que responda
con texto (o se llegue al tope de `MAX_VUELTAS`, para no dejar un pedido
girando en loop)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.almacen.base import AlmacenArchivos
from app.asistente.herramientas import catalogo_para_rol
from app.catalogo.tablas import Usuario, Workspace
from app.consultas.esquema import FiltroConsulta
from app.dashboard import operaciones as dashboard_operaciones
from app.inferencia.llm import ClienteLLM
from app.modelo import operaciones as modelo_operaciones
from app.modelo.esquema import ModeloSemantico
from app.nucleo.errores import ErrorApp

registro = logging.getLogger("uboard.asistente")

MAX_VUELTAS = 4
MAX_TOKENS_RESPUESTA = 2048

SISTEMA = """Sos el asistente de UBoard, un BI para pymes argentinas. Hablás en español
rioplatense, corto y directo. Según quién te pregunta tenés dos usos:

- Si tenés herramientas de escritura (crear_metrica, crear_grafico, etc.): la persona te
  pide cambios sobre el modelo o el dashboard en lenguaje natural ("agregá un gráfico de
  ventas por sucursal") y vos elegís y aplicás la o las operaciones que hacen falta.
  Cada herramienta hace UNA cosa; para un pedido con varios pasos, encadená varias
  llamadas. Fijate los ids reales en el contexto antes de inventar uno.
- Si solo tenés `consultar` y `aplicar_filtro`: la persona te hace una pregunta sobre los
  datos ("¿cuánto vendió Pérez en marzo?") y la respondés EXCLUSIVAMENTE con lo que te
  devuelve `consultar`. Nunca inventes ni calcules a mano un número.

Sobre `aplicar_filtro` (disponible en las dos situaciones si está en tus herramientas):
úsala cuando te pidan activar, cambiar o sacar un filtro que YA EXISTE en el dashboard
(mirá la lista de filtros del contexto, con su id, campo y tipo). "Aplicá el filtro de
ventas en efectivo" es `aplicar_filtro`, no `consultar`: la persona quiere ver el
dashboard entero filtrado, no solo la respuesta a una pregunta puntual. Si el filtro que
piden no existe todavía, no lo inventes ni lo simules con `consultar`: decile que hace
falta crearlo primero (si tenés `crear_filtro`, ofrecé crearlo).

Reglas para las dos situaciones:
- Si una herramienta devuelve un error, contale a la persona qué pasó en criollo, sin
  mostrar códigos internos ni tecnicismos; si podés, proponé cómo arreglarlo.
- No confirmes de más: si el pedido es ambiguo (por ejemplo, no está claro a qué métrica
  se refiere), preguntá antes de aplicar algo.
- No conocés los valores reales de un campo de texto (nombres, categorías): si te dan un
  nombre parcial ("Pérez", sin el nombre de pila) o un dato que puede estar escrito de
  otra forma, filtrá con el operador "contiene" en vez de "igual", así encontrás
  coincidencias aunque no tengas el valor exacto. Si "contiene" no encuentra nada, ahí sí
  preguntá por el dato exacto en vez de asumir que no hay resultados.
- Respuestas cortas. Al terminar una acción, contá en una frase qué quedó hecho."""


@dataclass
class AccionAplicada:
    herramienta: str
    entrada: dict[str, Any]
    resultado: str


@dataclass
class RespuestaAsistente:
    texto: str
    acciones: list[AccionAplicada] = field(default_factory=list)
    tokens_entrada: int = 0
    tokens_salida: int = 0


def _resumen_modelo(modelo: ModeloSemantico) -> dict[str, Any]:
    return {
        "entidades": [
            {
                "id": entidad.id,
                "nombre": entidad.nombre,
                "tipo": entidad.tipo,
                "campos": [
                    {"id": campo.id, "nombre": campo.nombre, "tipo_dato": campo.tipo_dato, "tipo_semantico": campo.tipo_semantico, "estado": campo.estado}
                    for campo in entidad.campos
                ],
            }
            for entidad in modelo.entidades
        ],
        "relaciones": [
            {"id": relacion.id, "desde": relacion.desde.referencia, "hacia": relacion.hacia.referencia, "estado": relacion.estado}
            for relacion in modelo.relaciones
        ],
        "metricas": [
            {"id": metrica.id, "nombre": metrica.nombre, "formato": metrica.formato, "estado": metrica.estado} for metrica in modelo.metricas
        ],
        "dimensiones_tiempo": [dimension.campo for dimension in modelo.dimensiones_tiempo],
    }


def _resumen_dashboard(spec) -> dict[str, Any]:
    return {
        "titulo": spec.titulo,
        "filtros": [{"id": filtro.id, "campo": filtro.campo, "tipo": filtro.tipo} for filtro in spec.filtros],
        "kpis": [{"id": kpi.id, "metrica": kpi.metrica, "titulo": kpi.titulo} for kpi in spec.kpis],
        "graficos": [{"id": grafico.id, "tipo": grafico.tipo, "metrica": grafico.metrica, "dimension": grafico.dimension} for grafico in spec.graficos],
        "pestanias": [{"entidad": pestania.entidad, "titulo": pestania.titulo} for pestania in spec.explorador.pestanias],
    }


def armar_contexto(sesion: Session, workspace: Workspace, filtros_activos: dict[str, Any] | None = None) -> str:
    """Lo que Claude necesita para saber que ids existen: el modelo completo
    (con estado, para poder confirmar/rechazar) y el dashboard si ya hay
    uno. JSON compacto, como el pedido de la inferencia (paso 11).
    `filtros_activos` (paso 21, crudo: {id_filtro: valor}) va aparte para
    que Claude pueda mencionarlos en la respuesta ("con los filtros que
    tenés activos..."); el filtrado real de `consultar` no depende de esto,
    lo aplica el motor sin importar si Claude lo nombra o no."""
    modelo = modelo_operaciones.modelo_de(modelo_operaciones.exigir_version_actual(sesion, workspace))
    contexto: dict[str, Any] = {"modelo": _resumen_modelo(modelo)}
    version_spec = dashboard_operaciones.version_actual(sesion, workspace)
    if version_spec is not None:
        contexto["dashboard"] = _resumen_dashboard(dashboard_operaciones.spec_de(version_spec))
    if filtros_activos:
        contexto["filtros_activos"] = filtros_activos
    return json.dumps(contexto, ensure_ascii=False, separators=(",", ":"), default=str)


def conversar(
    cliente: ClienteLLM,
    *,
    usuario: Usuario,
    sesion: Session,
    workspace: Workspace,
    almacen: AlmacenArchivos,
    mensaje: str,
    contexto: str,
    filtros_activos: list[FiltroConsulta] | None = None,
) -> RespuestaAsistente:
    """Un pedido de punta a punta: arma el catalogo de herramientas segun el
    rol, corre el loop de tool-use (tope de MAX_VUELTAS) y devuelve el texto
    final mas las acciones que aplico en el camino."""
    catalogo = catalogo_para_rol(usuario.rol, sesion=sesion, workspace=workspace, almacen=almacen, usuario=usuario, filtros_base=filtros_activos)
    mensajes: list[dict[str, Any]] = [{"role": "user", "content": f"Contexto actual: {contexto}\n\nPedido: {mensaje}"}]
    acciones: list[AccionAplicada] = []
    tokens_entrada = tokens_salida = 0

    for _ in range(MAX_VUELTAS):
        respuesta = cliente.conversar(sistema=SISTEMA, mensajes=mensajes, herramientas=catalogo.definiciones, max_tokens=MAX_TOKENS_RESPUESTA)
        tokens_entrada += respuesta.tokens_entrada
        tokens_salida += respuesta.tokens_salida
        if respuesta.es_final:
            return RespuestaAsistente(texto=respuesta.texto, acciones=acciones, tokens_entrada=tokens_entrada, tokens_salida=tokens_salida)

        mensajes.append({"role": "assistant", "content": respuesta.bloques})
        resultados: list[dict[str, Any]] = []
        for llamada in respuesta.llamadas:
            registro.info("asistente: workspace=%s usuario=%s herramienta=%s", workspace.id, usuario.id, llamada.nombre)
            try:
                resultado = catalogo.ejecutar(llamada.nombre, llamada.entrada)
                acciones.append(AccionAplicada(herramienta=llamada.nombre, entrada=llamada.entrada, resultado=resultado))
                resultados.append({"type": "tool_result", "tool_use_id": llamada.id, "content": resultado})
            except ErrorApp as error:
                registro.info("asistente: %s fallo con %s", llamada.nombre, error.codigo)
                resultados.append({"type": "tool_result", "tool_use_id": llamada.id, "content": f"{error.codigo}: {error.mensaje}", "is_error": True})
        mensajes.append({"role": "user", "content": resultados})

    raise ErrorApp("E-ASI-02", f"se llegó al límite de {MAX_VUELTAS} vueltas sin una respuesta final")
