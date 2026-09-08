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

export function useGrafico(opcion: EChartsOption | null) {
  const contenedor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const elemento = contenedor.current;
    if (!elemento) return;
    const instancia = echarts.getInstanceByDom(elemento) ?? echarts.init(elemento, undefined, { renderer: "canvas" });
    if (opcion) {
      instancia.setOption(opcion, true);
    } else {
      instancia.clear();
    }
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
