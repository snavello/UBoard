/* Traduce la respuesta de un grafico del dashboard a una opcion de ECharts,
   siguiendo las reglas del skill dataviz: marcas finas (barras <= 24 px con
   punta redondeada, lineas de 2 px), grilla hairline, texto siempre en tonos
   de tinta (nunca en el color de la serie), una sola serie sin leyenda,
   leyenda siempre para la torta, tooltip con el formato de la metrica. */
import type { EChartsOption } from "echarts";

import type { GraficoSalida } from "../../tipos";
import { SIN_DATO, etiquetaPeriodo, formatearCompacto, formatearMetrica } from "../formato";
import type { Tema } from "../tema";

const GROSOR_BARRA = 24;

function etiqueta(valor: unknown, grafico: GraficoSalida): string {
  if (valor === null || valor === undefined) return SIN_DATO;
  if (grafico.dimension.tipo === "fecha") return etiquetaPeriodo(valor, grafico.dimension.granularidad);
  return String(valor);
}

function ejeValor(grafico: GraficoSalida, tema: Tema) {
  return {
    type: "value" as const,
    axisLabel: { color: tema.mudo, fontFamily: tema.fuente, formatter: (valor: number) => formatearCompacto(valor, grafico.metrica.formato) },
    splitLine: { lineStyle: { color: tema.grilla, width: 1 } },
    axisLine: { show: false },
    axisTick: { show: false },
  };
}

function ejeCategoria(categorias: string[], tema: Tema, opciones: { inverso?: boolean; rotar?: boolean } = {}) {
  return {
    type: "category" as const,
    data: categorias,
    inverse: opciones.inverso ?? false,
    axisLabel: {
      color: tema.tinta2,
      fontFamily: tema.fuente,
      interval: 0,
      rotate: opciones.rotar ? 30 : 0,
      overflow: "truncate" as const,
      width: opciones.inverso ? 140 : undefined,
    },
    axisLine: { lineStyle: { color: tema.eje } },
    axisTick: { show: false },
  };
}

function tooltipBase(grafico: GraficoSalida, tema: Tema) {
  return {
    backgroundColor: tema.superficie,
    borderColor: tema.grilla,
    textStyle: { color: tema.tinta, fontFamily: tema.fuente },
    valueFormatter: (valor: unknown) => formatearMetrica(typeof valor === "number" ? valor : null, grafico.metrica.formato),
  };
}

export function opcionDeGrafico(grafico: GraficoSalida, tema: Tema): EChartsOption {
  if (grafico.tipo === "torta") return opcionTorta(grafico, tema);
  if (grafico.tipo === "linea") return opcionLinea(grafico, tema);
  return opcionBarras(grafico, tema);
}

function opcionLinea(grafico: GraficoSalida, tema: Tema): EChartsOption {
  const categorias = grafico.filas.map((fila) => etiqueta(fila[0], grafico));
  const valores = grafico.filas.map((fila) => fila[1]);
  return {
    animationDuration: 300,
    grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", ...tooltipBase(grafico, tema) },
    xAxis: { ...ejeCategoria(categorias, tema), boundaryGap: false },
    yAxis: ejeValor(grafico, tema),
    series: [
      {
        type: "line",
        name: grafico.metrica.nombre,
        data: valores,
        color: tema.serieUnica,
        lineStyle: { width: 2, cap: "round", join: "round" },
        symbol: "circle",
        symbolSize: 8,
        showSymbol: false,
        itemStyle: { borderColor: tema.superficie, borderWidth: 2 },
        areaStyle: { opacity: 0.1 },
        emphasis: { focus: "series" },
      },
    ],
  };
}

function opcionBarras(grafico: GraficoSalida, tema: Tema): EChartsOption {
  const categorias = grafico.filas.map((fila) => etiqueta(fila[0], grafico));
  const valores = grafico.filas.map((fila) => fila[1]);
  const horizontal = grafico.dimension.tipo !== "fecha";
  const pocas = valores.length <= 12;
  const serie = {
    type: "bar" as const,
    name: grafico.metrica.nombre,
    data: valores,
    color: tema.serieUnica,
    barMaxWidth: GROSOR_BARRA,
    itemStyle: { borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] },
    label: {
      show: pocas,
      position: horizontal ? ("right" as const) : ("top" as const),
      color: tema.tinta2,
      fontFamily: tema.fuente,
      formatter: (parametros: { value: unknown }) => formatearCompacto(Number(parametros.value ?? 0), grafico.metrica.formato),
    },
  };
  return {
    animationDuration: 300,
    grid: { left: 8, right: pocas && horizontal ? 64 : 16, top: 16, bottom: 8, containLabel: true },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, ...tooltipBase(grafico, tema) },
    xAxis: horizontal ? ejeValor(grafico, tema) : ejeCategoria(categorias, tema, { rotar: categorias.length > 8 }),
    yAxis: horizontal ? ejeCategoria(categorias, tema, { inverso: true }) : ejeValor(grafico, tema),
    series: [serie],
  };
}

function opcionTorta(grafico: GraficoSalida, tema: Tema): EChartsOption {
  const datos = grafico.filas.map((fila) => ({ name: etiqueta(fila[0], grafico), value: fila[1] ?? 0 }));
  return {
    animationDuration: 300,
    color: tema.series,
    tooltip: {
      trigger: "item",
      ...tooltipBase(grafico, tema),
      formatter: (parametros: unknown) => {
        const p = parametros as { name: string; value: number; percent: number };
        return `${p.name}<br/><strong>${formatearMetrica(p.value, grafico.metrica.formato)}</strong> · ${p.percent.toLocaleString("es-AR", { maximumFractionDigits: 1 })} %`;
      },
    },
    legend: {
      orient: "vertical",
      right: 0,
      top: "middle",
      icon: "circle",
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: tema.tinta2, fontFamily: tema.fuente },
    },
    series: [
      {
        type: "pie",
        name: grafico.metrica.nombre,
        radius: ["52%", "78%"],
        center: ["32%", "50%"],
        data: datos,
        label: { show: false },
        itemStyle: { borderColor: tema.superficie, borderWidth: 2 },
        emphasis: { scale: true, scaleSize: 4 },
      },
    ],
  };
}
