/* Los filtros activos viven en la URL (?filtros=<JSON>), igual que los
   recibe la API: el link del tablero es compartible y TanStack Query los usa
   como clave de cache. */
import type { FiltrosActivos } from "../tipos";

export const PARAMETRO_FILTROS = "filtros";

export function leerFiltros(parametros: URLSearchParams): FiltrosActivos {
  const crudo = parametros.get(PARAMETRO_FILTROS);
  if (!crudo) return {};
  try {
    const datos: unknown = JSON.parse(crudo);
    return datos && typeof datos === "object" && !Array.isArray(datos) ? (datos as FiltrosActivos) : {};
  } catch {
    return {};
  }
}

/** Quita los filtros vacios y devuelve el JSON para la URL, o null si no queda ninguno. */
export function serializarFiltros(filtros: FiltrosActivos): string | null {
  const limpios: FiltrosActivos = {};
  for (const [id, valor] of Object.entries(filtros)) {
    if (valor === null || valor === undefined) continue;
    if (Array.isArray(valor)) {
      if (valor.length === 0 || valor.every((extremo) => extremo === null || extremo === "")) continue;
      limpios[id] = valor.map((extremo) => (extremo === "" ? null : extremo));
    } else {
      limpios[id] = valor;
    }
  }
  return Object.keys(limpios).length ? JSON.stringify(limpios) : null;
}

export function escribirFiltros(parametros: URLSearchParams, filtros: FiltrosActivos): URLSearchParams {
  const nuevos = new URLSearchParams(parametros);
  const serializados = serializarFiltros(filtros);
  if (serializados) {
    nuevos.set(PARAMETRO_FILTROS, serializados);
  } else {
    nuevos.delete(PARAMETRO_FILTROS);
  }
  return nuevos;
}

export function cantidadActivos(filtros: FiltrosActivos): number {
  const serializados = serializarFiltros(filtros);
  return serializados ? Object.keys(JSON.parse(serializados) as FiltrosActivos).length : 0;
}
