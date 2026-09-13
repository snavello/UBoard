/* ECharts directo, sin wrapper: una instancia por div, se redimensiona con el
   contenedor y se destruye al desmontar. Solo se registran los graficos y
   componentes que usa el dashboard para no cargar la libreria entera. */
import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { EChartsOption } from "echarts";

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

/** `onClick`, si se pasa, se engancha al evento "click" de la serie (un
    punto de barras/torta/linea) con el `dataIndex` para que el llamador
    pueda mapearlo a la fila de datos original (paso A, click-to-filter). */
export function useGrafico(opcion: EChartsOption | null, onClick?: (dataIndex: number) => void) {
  const contenedor = useRef<HTMLDivElement>(null);
  const onClickRef = useRef(onClick);
  onClickRef.current = onClick;

  useEffect(() => {
    const elemento = contenedor.current;
    if (!elemento) return;
    const instancia = echarts.getInstanceByDom(elemento) ?? echarts.init(elemento, undefined, { renderer: "canvas" });
    if (opcion) {
      instancia.setOption(opcion, true);
    } else {
      instancia.clear();
    }
    instancia.off("click");
    instancia.on("click", (parametros) => {
      if (typeof parametros.dataIndex === "number") onClickRef.current?.(parametros.dataIndex);
    });
    const observador = new ResizeObserver(() => instancia.resize());
    observador.observe(elemento);
    return () => observador.disconnect();
  }, [opcion]);

  useEffect(() => {
    const elemento = contenedor.current;
    return () => {
      if (elemento) echarts.dispose(elemento);
    };
  }, []);

  return contenedor;
}
