/* Lee las variables CSS del sistema de diseño para pasarselas a ECharts, que
   no entiende var(--x). Se recalcula si cambia el esquema de color del SO. */
import { useEffect, useState } from "react";

import { serieUnica, series } from "./paleta";

export interface Tema {
  oscuro: boolean;
  tinta: string;
  tinta2: string;
  mudo: string;
  grilla: string;
  eje: string;
  superficie: string;
  papel: string;
  acento: string;
  fuente: string;
  series: string[];
  serieUnica: string;
}

function variable(nombre: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();
}

export function leerTema(): Tema {
  const oscuro = window.matchMedia("(prefers-color-scheme: dark)").matches;
  return {
    oscuro,
    tinta: variable("--tinta"),
    tinta2: variable("--tinta-2"),
    mudo: variable("--mudo"),
    grilla: variable("--grilla"),
    eje: variable("--eje"),
    superficie: variable("--superficie"),
    papel: variable("--papel"),
    acento: variable("--acento"),
    fuente: variable("--fuente-texto") || "system-ui, sans-serif",
    series: series(oscuro),
    serieUnica: serieUnica(oscuro),
  };
}

export function useTema(): Tema {
  const [tema, setTema] = useState<Tema>(() => leerTema());
  useEffect(() => {
    const consulta = window.matchMedia("(prefers-color-scheme: dark)");
    const actualizar = () => setTema(leerTema());
    consulta.addEventListener("change", actualizar);
    return () => consulta.removeEventListener("change", actualizar);
  }, []);
  return tema;
}
