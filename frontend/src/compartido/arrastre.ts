/* Arrastrar para reordenar (drag and drop nativo del navegador, sin
   libreria): separa las props del "agarradero" (el elemento chico que
   inicia el arrastre, `draggable`) de las del "contenedor" (el elemento
   grande que recibe el drop) porque algunos bloques (los graficos) tienen
   adentro sus propios manejadores de mouse (click-to-filter, paso A de la
   fase 4) y no conviene que todo el bloque sea arrastrable: un agarradero
   chico y quieto evita el conflicto. Donde no hay ese riesgo (una pestania,
   una cifra sin interaccion propia) el mismo elemento puede ser agarradero
   y contenedor a la vez. */
import { useState } from "react";

export interface ArrastreDeOrden {
  handleProps: (id: string) => {
    draggable: true;
    onDragStart: (evento: React.DragEvent) => void;
    onDragEnd: () => void;
  };
  contenedorProps: (id: string) => {
    onDragOver: (evento: React.DragEvent) => void;
    onDragLeave: () => void;
    onDrop: (evento: React.DragEvent) => void;
  };
  esDestino: (id: string) => boolean;
}

export function useArrastreDeOrden(mover: (idOrigen: string, idDestino: string) => void): ArrastreDeOrden {
  const [arrastrando, setArrastrando] = useState<string | null>(null);
  const [sobre, setSobre] = useState<string | null>(null);

  return {
    handleProps: (id) => ({
      draggable: true,
      onDragStart: (evento) => {
        evento.dataTransfer.effectAllowed = "move";
        evento.dataTransfer.setData("text/plain", id);
        setArrastrando(id);
      },
      onDragEnd: () => {
        setArrastrando(null);
        setSobre(null);
      },
    }),
    contenedorProps: (id) => ({
      onDragOver: (evento) => {
        if (!arrastrando || arrastrando === id) return;
        evento.preventDefault();
        setSobre(id);
      },
      onDragLeave: () => setSobre((actual) => (actual === id ? null : actual)),
      onDrop: (evento) => {
        evento.preventDefault();
        const idOrigen = evento.dataTransfer.getData("text/plain") || arrastrando;
        if (idOrigen && idOrigen !== id) mover(idOrigen, id);
        setArrastrando(null);
        setSobre(null);
      },
    }),
    esDestino: (id) => sobre === id,
  };
}
