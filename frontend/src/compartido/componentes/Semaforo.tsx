/* Semaforo de confianza para el wizard de revision: confirmada, rechazada, o
   propuesta con un nivel segun la confianza. Nunca solo color: cada nivel
   tiene tambien un icono y una palabra, para quien no distingue rojo/verde. */
import type { EstadoElemento } from "../../tipos";
import { formatearNumero } from "../formato";
import estilos from "./Semaforo.module.css";

export const UMBRAL_VERDE = 0.9;
export const UMBRAL_AMARILLO = 0.6;

export type NivelConfianza = "alta" | "media" | "baja";

export function nivelDeConfianza(confianza: number): NivelConfianza {
  if (confianza >= UMBRAL_VERDE) return "alta";
  if (confianza >= UMBRAL_AMARILLO) return "media";
  return "baja";
}

const ICONO: Record<NivelConfianza, string> = { alta: "●", media: "◐", baja: "○" };
const ETIQUETA: Record<NivelConfianza, string> = { alta: "Confianza alta", media: "Confianza media", baja: "Confianza baja" };

export function Semaforo({ estado, confianza }: { estado: EstadoElemento; confianza: number }) {
  if (estado === "confirmada") {
    return (
      <span className={`${estilos.chip} ${estilos.confirmada}`}>
        <span aria-hidden="true">✓</span> Confirmado
      </span>
    );
  }
  if (estado === "rechazada") {
    return (
      <span className={`${estilos.chip} ${estilos.rechazada}`}>
        <span aria-hidden="true">✕</span> Rechazado
      </span>
    );
  }
  const nivel = nivelDeConfianza(confianza);
  return (
    <span className={`${estilos.chip} ${estilos[nivel]}`} title={`${formatearNumero(confianza * 100, 0)} % de confianza`}>
      <span aria-hidden="true">{ICONO[nivel]}</span> {ETIQUETA[nivel]}
    </span>
  );
}
