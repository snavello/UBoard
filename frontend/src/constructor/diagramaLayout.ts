/* Calculo puro del layout del diagrama del modelo (tipo DER): entidades como
   cajas con sus campos, relaciones como conectores con notacion "pata de
   gallo" (crow's foot). El grafo de relaciones efectivas nunca tiene
   ciclos (lo garantiza `modelo/validacion.py`), asi que alcanza con un
   BFS por capas desde las entidades de "hechos" — sin necesitar una
   libreria de layout de grafos. */
import type { Campo, EntidadModelo, ModeloSemantico, RelacionModelo } from "../tipos";

export const ANCHO_CAJA = 220;
const ALTO_CABECERA = 40;
const ALTO_FILA = 24;
const PADDING_INFERIOR = 10;
export const ESPACIO_HORIZONTAL = 110;
const ESPACIO_VERTICAL = 36;
const ESPACIO_COMPONENTE = 56;

export interface FilaCampo {
  campo: Campo;
  esClave: boolean;
  y: number; // relativo al top de la caja
}

export interface CajaEntidad {
  entidad: EntidadModelo;
  x: number;
  y: number;
  ancho: number;
  alto: number;
  filas: FilaCampo[];
}

export type LadoCardinalidad = "uno" | "muchos";

export interface Conector {
  relacion: RelacionModelo;
  desde: { x: number; y: number; lado: LadoCardinalidad; direccion: 1 | -1 };
  hacia: { x: number; y: number; lado: LadoCardinalidad; direccion: 1 | -1 };
}

export interface LayoutDiagrama {
  cajas: CajaEntidad[];
  conectores: Conector[];
  ancho: number;
  alto: number;
}

function altoCaja(entidad: EntidadModelo): number {
  return ALTO_CABECERA + entidad.campos.length * ALTO_FILA + PADDING_INFERIOR;
}

export function ladosDeCardinalidad(cardinalidad: RelacionModelo["cardinalidad"]): { desde: LadoCardinalidad; hacia: LadoCardinalidad } {
  if (cardinalidad === "n:1") return { desde: "muchos", hacia: "uno" };
  if (cardinalidad === "1:n") return { desde: "uno", hacia: "muchos" };
  return { desde: "uno", hacia: "uno" };
}

/** BFS por capas a partir de las entidades de "hechos" (o cualquiera si no
    hay): agrupa por componente conexa, apilando las componentes una debajo
    de la otra. Devuelve entidad.id -> {capa, componente}. */
function calcularCapas(modelo: ModeloSemantico): Map<string, { capa: number; componente: number }> {
  const vecinos = new Map<string, string[]>();
  for (const entidad of modelo.entidades) vecinos.set(entidad.id, []);
  for (const relacion of modelo.relaciones) {
    vecinos.get(relacion.desde.entidad)?.push(relacion.hacia.entidad);
    vecinos.get(relacion.hacia.entidad)?.push(relacion.desde.entidad);
  }

  const ubicacion = new Map<string, { capa: number; componente: number }>();
  const pendientes = [...modelo.entidades].sort((a, b) => (a.tipo === b.tipo ? 0 : a.tipo === "hechos" ? -1 : 1)).map((e) => e.id);
  let componente = 0;
  for (const inicio of pendientes) {
    if (ubicacion.has(inicio)) continue;
    let capaActual = [inicio];
    let capa = 0;
    ubicacion.set(inicio, { capa, componente });
    while (capaActual.length > 0) {
      const siguienteCapa: string[] = [];
      for (const id of capaActual) {
        for (const vecino of vecinos.get(id) ?? []) {
          if (!ubicacion.has(vecino)) {
            ubicacion.set(vecino, { capa: capa + 1, componente });
            siguienteCapa.push(vecino);
          }
        }
      }
      capaActual = siguienteCapa;
      capa += 1;
    }
    componente += 1;
  }
  return ubicacion;
}

export function calcularLayout(modelo: ModeloSemantico): LayoutDiagrama {
  const ubicacion = calcularCapas(modelo);

  // Agrupar por componente y capa para poder apilar cada componente aparte.
  const porComponente = new Map<number, Map<number, string[]>>();
  for (const entidad of modelo.entidades) {
    const { capa, componente } = ubicacion.get(entidad.id)!;
    if (!porComponente.has(componente)) porComponente.set(componente, new Map());
    const capas = porComponente.get(componente)!;
    if (!capas.has(capa)) capas.set(capa, []);
    capas.get(capa)!.push(entidad.id);
  }

  const cajasPorId = new Map<string, CajaEntidad>();
  let yComponente = 0;
  let anchoMaximo = 0;

  for (const capas of porComponente.values()) {
    let altoComponente = 0;
    for (const [capa, idsCapa] of capas) {
      let yCursor = 0;
      for (const id of idsCapa) {
        const entidad = modelo.entidades.find((e) => e.id === id)!;
        const alto = altoCaja(entidad);
        const x = capa * (ANCHO_CAJA + ESPACIO_HORIZONTAL);
        const y = yComponente + yCursor;
        const filas: FilaCampo[] = entidad.campos.map((campo, indice) => ({
          campo,
          esClave: entidad.clave_primaria.includes(campo.id),
          y: ALTO_CABECERA + indice * ALTO_FILA + ALTO_FILA / 2,
        }));
        cajasPorId.set(id, { entidad, x, y, ancho: ANCHO_CAJA, alto, filas });
        yCursor += alto + ESPACIO_VERTICAL;
        anchoMaximo = Math.max(anchoMaximo, x + ANCHO_CAJA);
      }
      altoComponente = Math.max(altoComponente, yCursor - ESPACIO_VERTICAL);
    }
    yComponente += altoComponente + ESPACIO_COMPONENTE;
  }

  const conectores: Conector[] = [];
  for (const relacion of modelo.relaciones) {
    const cajaDesde = cajasPorId.get(relacion.desde.entidad);
    const cajaHacia = cajasPorId.get(relacion.hacia.entidad);
    if (!cajaDesde || !cajaHacia) continue;
    const filaDesde = cajaDesde.filas.find((f) => f.campo.id === relacion.desde.campo);
    const filaHacia = cajaHacia.filas.find((f) => f.campo.id === relacion.hacia.campo);
    if (!filaDesde || !filaHacia) continue;
    const haciaEstaALaDerecha = cajaHacia.x >= cajaDesde.x;
    const lados = ladosDeCardinalidad(relacion.cardinalidad);
    conectores.push({
      relacion,
      desde: {
        x: cajaDesde.x + (haciaEstaALaDerecha ? cajaDesde.ancho : 0),
        y: cajaDesde.y + filaDesde.y,
        lado: lados.desde,
        direccion: haciaEstaALaDerecha ? 1 : -1,
      },
      hacia: {
        x: cajaHacia.x + (haciaEstaALaDerecha ? 0 : cajaHacia.ancho),
        y: cajaHacia.y + filaHacia.y,
        lado: lados.hacia,
        direccion: haciaEstaALaDerecha ? -1 : 1,
      },
    });
  }

  return {
    cajas: [...cajasPorId.values()],
    conectores,
    ancho: anchoMaximo,
    alto: yComponente - ESPACIO_COMPONENTE,
  };
}
