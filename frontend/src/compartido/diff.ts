/* El diff que guarda cada version (modelo y dashboard, mismo formato):
   por coleccion, ids agregados/quitados/cambiados; algunas colecciones
   (por ahora solo "titulo") son un cambio simple {anterior, nuevo}. */
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
