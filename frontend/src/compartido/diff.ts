/* El diff que guarda cada version (modelo y dashboard, mismo formato):
   por coleccion, ids agregados/quitados/cambiados; algunas colecciones
   (por ahora solo "titulo") son un cambio simple {anterior, nuevo}. */
import type { DiffEsquema } from "../tipos";

type ColeccionDiff = { agregados?: string[]; quitados?: string[]; cambiados?: string[] };
type CambioSimple = { anterior: unknown; nuevo: unknown };

function esCambioSimple(valor: unknown): valor is CambioSimple {
  return typeof valor === "object" && valor !== null && "anterior" in valor && "nuevo" in valor;
}

/** Una linea legible por coleccion que cambio, para mostrar bajo cada version
    del historial. Ninguna linea si no hubo diff (primera version). */
export function resumirDiff(diff: Record<string, unknown> | null | undefined): string[] {
  if (!diff) return [];
  const lineas: string[] = [];
  for (const [coleccion, valor] of Object.entries(diff)) {
    if (esCambioSimple(valor)) {
      lineas.push(`${coleccion}: "${valor.anterior ?? "—"}" → "${valor.nuevo ?? "—"}"`);
      continue;
    }
    const { agregados = [], quitados = [], cambiados = [] } = (valor ?? {}) as ColeccionDiff;
    const partes: string[] = [];
    if (agregados.length) partes.push(`+${agregados.join(", ")}`);
    if (quitados.length) partes.push(`−${quitados.join(", ")}`);
    if (cambiados.length) partes.push(`~${cambiados.join(", ")}`);
    if (partes.length) lineas.push(`${coleccion}: ${partes.join(" · ")}`);
  }
  return lineas;
}

/** El diff de esquema de una resubida (fase 4, "resubida con deteccion de
    cambios"): resumen en una linea, mismo signo +/−/~ que `resumirDiff`, mas
    una advertencia aparte cuando el modelo semantico usaba una columna que
    la resubida se llevo puesta (el caso que de verdad importa). */
export function resumirDiffEsquema(diff: DiffEsquema): { resumen: string; advertencia: string | null } {
  const partes: string[] = [];
  if (diff.columnas_nuevas.length) partes.push(`+${diff.columnas_nuevas.join(", ")}`);
  if (diff.columnas_perdidas.length) partes.push(`−${diff.columnas_perdidas.join(", ")}`);
  if (diff.columnas_tipo_cambiado.length) {
    partes.push(`~${diff.columnas_tipo_cambiado.map((cambio) => `${cambio.nombre} (${cambio.tipo_anterior}→${cambio.tipo_nuevo})`).join(", ")}`);
  }
  const deltaFilas = diff.filas_despues - diff.filas_antes;
  if (deltaFilas !== 0) partes.push(`${deltaFilas > 0 ? "+" : ""}${deltaFilas} filas`);

  const advertencia = diff.columnas_perdidas_en_uso.length
    ? `Tu modelo usa ${diff.columnas_perdidas_en_uso.join(", ")}, que ya no ${diff.columnas_perdidas_en_uso.length === 1 ? "está" : "están"} en el archivo nuevo.`
    : null;
  return { resumen: partes.length ? partes.join(" · ") : "Sin cambios de esquema.", advertencia };
}
