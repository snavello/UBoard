/* Orden personal de un bloque del tablero (KPIs, graficos, pestanias del
   explorador): pedido de Sd para poder "mover y reubicar" cada uno y armar
   su propio orden de lectura. A proposito NO viaja al backend ni entra al
   spec versionado del dashboard (eso es la estructura compartida por toda
   la organizacion, con su propio historial); es una preferencia personal,
   guardada en el navegador de esta persona para este workspace. Por eso
   tampoco se sincroniza entre dispositivos - version simple, elegida por
   Sd sobre la alternativa de sumar una tabla nueva en el backend.

   El arrastre se ve "en vivo": mientras se arrastra, `vistaPrevia` va
   corriendo los demas elementos para hacerle lugar (recalculada en cada
   `dragover`), y recien al soltar se persiste. Si se suelta afuera de
   cualquier elemento valido, `onDragEnd` descarta la vista previa sin
   persistir nada: vuelve a quedar como estaba. Primera version (antes de
   que Sd la probara) solo dejaba insertar ANTES del elemento soltado, asi
   que mover algo al final de la lista era imposible y se sentia como
   "intercambiar" en vez de reordenar libre; ahora `ladoDeSoltar` decide
   antes/despues segun en que mitad del elemento se suelta. */
import { useEffect, useState } from "react";

import { ladoDeSoltar } from "./arrastre";
import { useSesion } from "./sesion";

function claveOrden(tipo: string, workspaceId: number, usuarioId: number): string {
  return `uboard:orden:${tipo}:${workspaceId}:${usuarioId}`;
}

function leerOrdenGuardado(clave: string): string[] | null {
  try {
    const crudo = localStorage.getItem(clave);
    if (!crudo) return null;
    const datos: unknown = JSON.parse(crudo);
    return Array.isArray(datos) && datos.every((id) => typeof id === "string") ? (datos as string[]) : null;
  } catch {
    return null;
  }
}

function guardarOrden(clave: string, orden: string[]): void {
  try {
    localStorage.setItem(clave, JSON.stringify(orden));
  } catch {
    // localStorage puede fallar (navegacion privada, cuota llena): el orden
    // queda solo en memoria para esta pantalla, sin romper nada.
  }
}

/** El orden guardado, ajustado a los ids que hay AHORA: los conocidos
    mantienen su posicion relativa, los nuevos (el spec trajo un elemento
    que no estaba la ultima vez) van al final, y los que ya no existen se
    ignoran sin romper el resto. Pura, sin tocar el navegador. */
export function combinarOrden(guardado: string[], idsActuales: string[]): string[] {
  return [...guardado.filter((id) => idsActuales.includes(id)), ...idsActuales.filter((id) => !guardado.includes(id))];
}

/** Mueve `idOrigen` justo antes o despues de `idDestino` (`lado`). Si
    alguno de los dos no esta en `orden`, o son el mismo, devuelve `orden`
    tal cual. Pura, misma razon que `combinarOrden`. */
export function moverEnOrden(orden: string[], idOrigen: string, idDestino: string, lado: "antes" | "despues" = "antes"): string[] {
  if (idOrigen === idDestino || !orden.includes(idOrigen) || !orden.includes(idDestino)) return orden;
  const sinOrigen = orden.filter((id) => id !== idOrigen);
  const indiceDestino = sinOrigen.indexOf(idDestino);
  const indiceInsercion = lado === "antes" ? indiceDestino : indiceDestino + 1;
  return [...sinOrigen.slice(0, indiceInsercion), idOrigen, ...sinOrigen.slice(indiceInsercion)];
}

export interface ControlesArrastre {
  handleProps: (id: string) => {
    draggable: true;
    onDragStart: (evento: React.DragEvent) => void;
    onDragEnd: () => void;
  };
  contenedorProps: (id: string) => {
    onDragOver: (evento: React.DragEvent) => void;
    onDrop: (evento: React.DragEvent) => void;
  };
  /** null si no se esta arrastrando nada sobre este id ahora mismo. */
  ladoDestino: (id: string) => "antes" | "despues" | null;
}

/** Reordena "items" segun la preferencia guardada para este workspace y
    usuario, con arrastre en vivo. Devuelve la lista ya reordenada (la
    vista previa mientras se arrastra, o el orden persistido en reposo) y
    los controles para conectar el drag and drop de cada elemento. */
export function useOrdenPersonal<T>(tipo: string, workspaceId: number, items: T[], idDe: (item: T) => string): [T[], ControlesArrastre] {
  const { usuario } = useSesion();
  const clave = claveOrden(tipo, workspaceId, usuario?.id ?? 0);
  const [ordenGuardado, setOrdenGuardado] = useState<string[]>(() => leerOrdenGuardado(clave) ?? []);
  const [vistaPrevia, setVistaPrevia] = useState<string[] | null>(null);
  const [arrastrando, setArrastrando] = useState<string | null>(null);
  const [destino, setDestino] = useState<{ id: string; lado: "antes" | "despues" } | null>(null);

  useEffect(() => {
    setOrdenGuardado(leerOrdenGuardado(clave) ?? []);
  }, [clave]);

  const idsActuales = items.map(idDe);
  const ordenBase = combinarOrden(ordenGuardado, idsActuales);
  const ordenEfectivo = vistaPrevia ?? ordenBase;

  const porId = new Map(items.map((item) => [idDe(item), item]));
  const ordenados = ordenEfectivo.map((id) => porId.get(id)).filter((item): item is T => item !== undefined);

  const controles: ControlesArrastre = {
    handleProps: (id) => ({
      draggable: true,
      onDragStart: (evento) => {
        evento.dataTransfer.effectAllowed = "move";
        evento.dataTransfer.setData("text/plain", id);
        setArrastrando(id);
        setVistaPrevia(ordenBase);
      },
      onDragEnd: () => {
        // Si `onDrop` ya persistio, esto solo limpia el estado transitorio;
        // si se solto afuera de cualquier elemento valido, descarta la
        // vista previa sin guardar nada (vuelve a `ordenBase`).
        setArrastrando(null);
        setVistaPrevia(null);
        setDestino(null);
      },
    }),
    contenedorProps: (id) => ({
      onDragOver: (evento) => {
        if (!arrastrando || arrastrando === id) return;
        evento.preventDefault();
        const rect = evento.currentTarget.getBoundingClientRect();
        const lado = ladoDeSoltar(evento.clientX, evento.clientY, rect);
        setDestino({ id, lado });
        setVistaPrevia((actual) => moverEnOrden(actual ?? ordenBase, arrastrando, id, lado));
      },
      onDrop: (evento) => {
        evento.preventDefault();
        const nuevo = vistaPrevia ?? ordenBase;
        setOrdenGuardado(nuevo);
        guardarOrden(clave, nuevo);
        setArrastrando(null);
        setVistaPrevia(null);
        setDestino(null);
      },
    }),
    ladoDestino: (id) => (destino?.id === id ? destino.lado : null),
  };

  return [ordenados, controles];
}
