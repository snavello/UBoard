"""Claude cura el spec base (paso 14): elige el KPI protagonista, descarta
graficos redundantes, pone titulos claros y ordena todo de mayor a menor
interes. Nunca inventa ids, ni cambia a que metrica o campo apunta un panel:
eso ya lo decidio el generador determinista (`generador.py`) a partir de lo
que el usuario confirmo en el wizard.
"""
from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from app.dashboard.esquema import SpecDashboard
from app.inferencia.llm import ClienteLLM, RespuestaLLM
from app.modelo.esquema import ModeloSemantico
from app.nucleo.errores import ErrorApp

MAX_TOKENS_SPEC = 3000

SISTEMA = """Sos parte de UBoard, un BI para pymes argentinas. Te paso un dashboard BASE
generado automaticamente a partir de un modelo de datos: ya tiene los filtros, KPIs,
graficos y pestanas del explorador armados y funcionando. Tu trabajo es CURARLO:
- Elegir que KPI es el protagonista (va primero en la lista; el resto en el orden
  que tenga mas sentido para un gerente que abre el tablero por primera vez).
- Para cada grafico, decidir si vale la pena mostrarlo (`incluir`) y ponerle un
  titulo corto y claro en castellano rioplatense (ej. "Ventas por mes", no
  "Total ventas agrupado por fecha de venta"). Descartá un grafico si es
  redundante con otro o si no aporta nada de negocio.
- Poner una etiqueta corta a cada filtro (ej. "Período", "Sucursal").
- Poner un titulo a cada pestana del explorador (el nombre de la entidad, en
  plural si corresponde: "Ventas", "Productos").
- Poner un titulo general al dashboard (el rubro del negocio si se nota en los
  nombres, si no algo generico como "Panel de ventas").
Reglas que no podes romper:
- Usá EXACTAMENTE los ids que te paso, no inventes ninguno. No agregues filtros,
  KPIs, graficos ni pestanas nuevas: si un id no aparece en tu respuesta, se
  descarta (para filtros, KPIs y pestanas eso esta mal: tienen que estar todos).
  Para graficos SI podes marcar `incluir: false` en vez de omitirlos.
- No cambies a que metrica, campo o entidad apunta nada: eso ya esta decidido."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FiltroCurado(_Base):
    id: str
    etiqueta: str = Field(min_length=1, max_length=60)


class KpiCurado(_Base):
    id: str
    titulo: str = Field(min_length=1, max_length=60)


class GraficoCurado(_Base):
    id: str
    titulo: str = Field(min_length=1, max_length=80)
    incluir: bool = True


class PestaniaCurada(_Base):
    entidad: str
    titulo: str = Field(min_length=1, max_length=60)


class SpecCurado(_Base):
    titulo: str = Field(min_length=1, max_length=80)
    filtros: list[FiltroCurado]
    kpis: list[KpiCurado]
    graficos: list[GraficoCurado]
    pestanias: list[PestaniaCurada]


def _describir_grafico(spec: SpecDashboard, modelo: ModeloSemantico, grafico) -> dict:
    metrica = modelo.metrica(grafico.metrica)
    resuelto = modelo.resolver_campo(grafico.dimension)
    return {
        "id": grafico.id,
        "tipo": grafico.tipo,
        "metrica": metrica.nombre if metrica else grafico.metrica,
        "dimension": resuelto[1].nombre if resuelto else grafico.dimension,
        "granularidad": grafico.granularidad,
    }


def armar_pedido(spec: SpecDashboard, modelo: ModeloSemantico) -> str:
    pedido = {
        "filtros": [{"id": f.id, "campo": modelo.resolver_campo(f.campo)[1].nombre if modelo.resolver_campo(f.campo) else f.campo, "tipo": f.tipo} for f in spec.filtros],
        "kpis": [{"id": k.id, "metrica": (modelo.metrica(k.metrica).nombre if modelo.metrica(k.metrica) else k.metrica)} for k in spec.kpis],
        "graficos": [_describir_grafico(spec, modelo, g) for g in spec.graficos],
        "pestanias": [{"entidad": p.entidad, "nombre": (modelo.entidad(p.entidad).nombre if modelo.entidad(p.entidad) else p.entidad)} for p in spec.explorador.pestanias],
    }
    return json.dumps(pedido, ensure_ascii=False, separators=(",", ":"), default=str)


def huella_pedido(modelo_claude: str, sistema: str, pedido: str) -> str:
    return hashlib.sha256(f"{modelo_claude}|{sistema}|{pedido}".encode()).hexdigest()[:32]


def validar_curacion(spec: SpecDashboard, curado: SpecCurado) -> list[str]:
    errores: list[str] = []

    def _chequear(nombre: str, ids_validos: set[str], vistos: list[str]) -> None:
        desconocidos = [identificador for identificador in vistos if identificador not in ids_validos]
        if desconocidos:
            errores.append(f"{nombre} usa id(s) que no existen: {', '.join(desconocidos)}")
        repetidos = {identificador for identificador in vistos if vistos.count(identificador) > 1}
        if repetidos:
            errores.append(f"{nombre} repite id(s): {', '.join(sorted(repetidos))}")

    _chequear("filtros", {f.id for f in spec.filtros}, [f.id for f in curado.filtros])
    _chequear("kpis", {k.id for k in spec.kpis}, [k.id for k in curado.kpis])
    _chequear("graficos", {g.id for g in spec.graficos}, [g.id for g in curado.graficos])
    _chequear("pestanias", {p.entidad for p in spec.explorador.pestanias}, [p.entidad for p in curado.pestanias])

    faltantes_filtros = {f.id for f in spec.filtros} - {f.id for f in curado.filtros}
    if faltantes_filtros:
        errores.append(f"faltan filtros (tienen que estar todos): {', '.join(sorted(faltantes_filtros))}")
    faltantes_kpis = {k.id for k in spec.kpis} - {k.id for k in curado.kpis}
    if faltantes_kpis:
        errores.append(f"faltan KPIs (tienen que estar todos): {', '.join(sorted(faltantes_kpis))}")
    faltantes_pestanias = {p.entidad for p in spec.explorador.pestanias} - {p.entidad for p in curado.pestanias}
    if faltantes_pestanias:
        errores.append(f"faltan pestañas (tienen que estar todas): {', '.join(sorted(faltantes_pestanias))}")
    faltantes_graficos = {g.id for g in spec.graficos} - {g.id for g in curado.graficos}
    if faltantes_graficos:
        errores.append(f"faltan gráficos (tienen que estar todos, usá incluir=false para descartar uno): {', '.join(sorted(faltantes_graficos))}")
    return errores


def consultar_curacion(cliente: ClienteLLM, spec: SpecDashboard, pedido: str) -> tuple[SpecCurado, RespuestaLLM]:
    """Mismo patron que la semantica del modelo: reintenta una vez con el
    error como feedback; a la segunda falla, E-SPEC-06."""
    usuario = pedido
    ultima: RespuestaLLM | None = None
    errores: list[str] = []
    for intento in range(2):
        if intento == 1:
            usuario = pedido + "\n\nTu respuesta anterior tenía estos errores; corregilos y devolvé la respuesta completa de nuevo:\n- " + "\n- ".join(errores)
        ultima = cliente.completar(sistema=SISTEMA, usuario=usuario, esquema=SpecCurado, max_tokens=MAX_TOKENS_SPEC)
        curado = SpecCurado.model_validate(ultima.contenido)
        errores = validar_curacion(spec, curado)
        if not errores:
            return curado, ultima
    raise ErrorApp("E-SPEC-06", "; ".join(errores[:5]))


def aplicar_curacion(spec: SpecDashboard, curado: SpecCurado) -> SpecDashboard:
    """Reordena, filtra y titula el spec base segun lo que dijo Claude. Los
    ids, campos y metricas de cada panel no cambian: solo orden, titulo, e
    `incluir` en graficos."""
    spec = spec.model_copy(deep=True)
    spec.titulo = curado.titulo

    etiquetas = {f.id: f.etiqueta for f in curado.filtros}
    orden_filtros = {f.id: posicion for posicion, f in enumerate(curado.filtros)}
    for filtro in spec.filtros:
        if filtro.id in etiquetas:
            filtro.etiqueta = etiquetas[filtro.id]
    spec.filtros.sort(key=lambda f: orden_filtros.get(f.id, len(orden_filtros)))

    titulos_kpi = {k.id: k.titulo for k in curado.kpis}
    orden_kpis = {k.id: posicion for posicion, k in enumerate(curado.kpis)}
    for kpi in spec.kpis:
        if kpi.id in titulos_kpi:
            kpi.titulo = titulos_kpi[kpi.id]
    spec.kpis.sort(key=lambda k: orden_kpis.get(k.id, len(orden_kpis)))

    incluidos = {g.id for g in curado.graficos if g.incluir}
    titulos_grafico = {g.id: g.titulo for g in curado.graficos}
    orden_graficos = {g.id: posicion for posicion, g in enumerate(curado.graficos)}
    graficos_curados = [g for g in spec.graficos if g.id in incluidos]
    for grafico in graficos_curados:
        if grafico.id in titulos_grafico:
            grafico.titulo = titulos_grafico[grafico.id]
    graficos_curados.sort(key=lambda g: orden_graficos.get(g.id, len(orden_graficos)))
    spec.graficos = graficos_curados

    titulos_pestania = {p.entidad: p.titulo for p in curado.pestanias}
    orden_pestanias = {p.entidad: posicion for posicion, p in enumerate(curado.pestanias)}
    for pestania in spec.explorador.pestanias:
        if pestania.entidad in titulos_pestania:
            pestania.titulo = titulos_pestania[pestania.entidad]
    spec.explorador.pestanias.sort(key=lambda p: orden_pestanias.get(p.entidad, len(orden_pestanias)))

    return spec
