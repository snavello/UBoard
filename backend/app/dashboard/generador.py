"""Generador determinista del spec base del dashboard (fase 2, paso 14).

Parte enteramente del modelo EFECTIVO (lo confirmado, o propuesto por encima
del umbral): una métrica de cada una se vuelve KPI; la primera dimensión de
tiempo, un gráfico de línea con su filtro de rango; hasta tres campos
`categoria` con menos valores distintos, gráficos de barras con su filtro de
lista; una pestaña de explorador por entidad con sus campos propios (menos
la clave, que ya viaja oculta). Es lo que se guarda si Claude falla o no hay
clave (`inferencia/spec.py`, paso 14): el dashboard nunca queda vacío si el
modelo tiene algo confirmado.

Una métrica no se puede desglosar por cualquier dimensión sin multiplicar
filas (§7): para el gráfico de línea y cada barra, se prueba compilar de
verdad (`Compilador`, sin ejecutar) con las métricas confirmadas hasta
encontrar una que funcione con esa dimensión; si ninguna funciona, esa
dimensión se descarta en vez de generar un gráfico inválido.
"""
from __future__ import annotations

from app.consultas.compilador import Compilador
from app.dashboard import paneles
from app.dashboard.esquema import ExploradorSpec, FiltroSpec, GraficoSpec, KpiSpec, PestaniaSpec, SpecDashboard
from app.modelo.esquema import Campo, Entidad, ModeloSemantico
from app.nucleo.errores import ErrorApp

MAXIMO_GRAFICOS_CATEGORIA = 3
GRANULARIDAD_POR_DEFECTO = "mes"


def _id_libre(usados: set[str], base: str) -> str:
    candidato = base[:60] or "x"
    contador = 2
    while candidato in usados:
        candidato = f"{base[:56]}_{contador}"
        contador += 1
    usados.add(candidato)
    return candidato


def _distintos(campo: Campo) -> int:
    """Cardinalidad guardada en la evidencia de la heurística (paso 10) o de
    Claude; si no está (métrica creada a mano), se la manda al final."""
    valor = campo.evidencia.get("distintos")
    return valor if isinstance(valor, int) and valor > 1 else 10**9


def _campos_categoria(modelo: ModeloSemantico) -> list[tuple[Entidad, Campo]]:
    """Campos `categoria` de todo el modelo, del que agrupa en menos grupos
    (más útil para un gráfico de barras) al que agrupa en más."""
    candidatos = [
        (entidad, campo) for entidad in modelo.entidades for campo in entidad.campos if campo.tipo_semantico == "categoria"
    ]
    candidatos.sort(key=lambda par: _distintos(par[1]))
    return candidatos


def _compila(compilador: Compilador, grafico: GraficoSpec) -> bool:
    """Prueba real contra el compilador (sin ejecutar): no toda métrica se
    puede desglosar por cualquier dimensión sin multiplicar filas (§7). Se
    usa para elegir, entre las métricas confirmadas, una que sí funcione con
    cada dimensión candidata."""
    try:
        compilador.compilar(paneles.consulta_grafico(grafico, []))
        return True
    except ErrorApp:
        return False


def _elegir_metrica(compilador: Compilador, metricas: list[str], grafico_de_prueba) -> str | None:
    """La primera métrica (en el orden del modelo) que compila con esa
    dimensión; `metricas` ya viene con la preferida primero."""
    for metrica_id in metricas:
        if _compila(compilador, grafico_de_prueba(metrica_id)):
            return metrica_id
    return None


def generar_spec_base(modelo: ModeloSemantico) -> SpecDashboard:
    """`modelo` tiene que ser el efectivo (`modelo_efectivo(...)`), no el
    completo: lo que no entra al dashboard no puede aparecer en el spec."""
    ids: set[str] = set()
    filtros: list[FiltroSpec] = []
    kpis: list[KpiSpec] = []
    graficos: list[GraficoSpec] = []
    compilador = Compilador(modelo)
    ids_metrica = [metrica.id for metrica in modelo.metricas]

    for metrica in modelo.metricas:
        kpis.append(KpiSpec(id=_id_libre(ids, f"k_{metrica.id}"), metrica=metrica.id))

    if modelo.dimensiones_tiempo:
        dimension = modelo.dimensiones_tiempo[0]
        granularidad = GRANULARIDAD_POR_DEFECTO if GRANULARIDAD_POR_DEFECTO in dimension.granularidades else dimension.granularidades[0]
        sufijo = dimension.campo.replace(".", "_")
        metrica_linea = _elegir_metrica(
            compilador,
            ids_metrica,
            lambda metrica_id: GraficoSpec(id="prueba", tipo="linea", metrica=metrica_id, dimension=dimension.campo, granularidad=granularidad),
        )
        if metrica_linea:
            filtros.append(FiltroSpec(id=_id_libre(ids, f"f_{sufijo}"), campo=dimension.campo, tipo="rango_fecha"))
            graficos.append(
                GraficoSpec(id=_id_libre(ids, f"g_{sufijo}"), tipo="linea", metrica=metrica_linea, dimension=dimension.campo, granularidad=granularidad)
            )

    agregados = 0
    for entidad, campo in _campos_categoria(modelo):
        if agregados >= MAXIMO_GRAFICOS_CATEGORIA:
            break
        referencia = f"{entidad.id}.{campo.id}"
        # Preferir la misma metrica que uso el grafico de linea (consistencia visual)
        orden_preferido = ([graficos[0].metrica] if graficos else []) + ids_metrica
        metrica_barra = _elegir_metrica(
            compilador, orden_preferido, lambda metrica_id, referencia=referencia: GraficoSpec(id="prueba", tipo="barras", metrica=metrica_id, dimension=referencia, top=10)
        )
        if metrica_barra is None:
            continue
        filtros.append(FiltroSpec(id=_id_libre(ids, f"f_{campo.id}"), campo=referencia, tipo="lista"))
        graficos.append(GraficoSpec(id=_id_libre(ids, f"g_{campo.id}"), tipo="barras", metrica=metrica_barra, dimension=referencia, top=10))
        agregados += 1

    pestanias: list[PestaniaSpec] = []
    for entidad in modelo.entidades:
        columnas = [campo.id for campo in entidad.campos if campo.id not in entidad.clave_primaria]
        if columnas:
            pestanias.append(PestaniaSpec(entidad=entidad.id, columnas=columnas))

    return SpecDashboard(filtros=filtros, kpis=kpis, graficos=graficos, explorador=ExploradorSpec(pestanias=pestanias))
