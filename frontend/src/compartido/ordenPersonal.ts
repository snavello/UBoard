/* Orden personal de un bloque del tablero (KPIs, graficos, pestanias del
   explorador): pedido de Sd para poder "mover y reubicar" cada uno y armar
   su propio orden de lectura. A proposito NO viaja al backend ni entra al
   spec versionado del dashboard (eso es la estructura compartida por toda
   la organizacion, con su propio historial); es una preferencia personal,
   guardada en el navegador de esta persona para este workspace. Por eso
   tampoco se sincroniza entre dispositivos - version simple, elegida por
   Sd sobre la alternativa de sumar una tabla nueva en el backend. */
import { useEffect, useState } from "react";

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
    ignoran sin romper el resto. Pura, sin tocar el navegador: probada
    aparte en `ordenPersonal.test.ts`. */
export function combinarOrden(guardado: string[], idsActuales: string[]): string[] {
  return [...guardado.filter((id) => idsActuales.includes(id)), ...idsActuales.filter((id) => !guardado.includes(id))];
}

/** Mueve `idOrigen` justo antes de `idDestino`. Si alguno de los dos no
    esta en `orden`, o son el mismo, devuelve `orden` tal cual (no hay nada
    que mover). Pura, misma razon que `combinarOrden`. */
export function moverEnOrden(orden: string[], idOrigen: string, idDestino: string): string[] {
  if (idOrigen === idDestino || !orden.includes(idOrigen) || !orden.includes(idDestino)) return orden;
  const sinOrigen = orden.filter((id) => id !== idOrigen);
  const posicion = sinOrigen.indexOf(idDestino);
  return [...sinOrigen.slice(0, posicion), idOrigen, ...sinOrigen.slice(posicion)];
}

/** Reordena "items" segun la preferencia guardada para este workspace y
    usuario. Devuelve la lista ya reordenada y una funcion
    `mover(idOrigen, idDestino)` que la persona dispara al soltar un
    elemento arrastrado justo antes de otro. */
export function useOrdenPersonal<T>(tipo: string, workspaceId: number, items: T[], idDe: (item: T) => string): [T[], (idOrigen: string, idDestino: string) => void] {
  const { usuario } = useSesion();
  const clave = claveOrden(tipo, workspaceId, usuario?.id ?? 0);
  const [ordenGuardado, setOrdenGuardado] = useState<string[]>(() => leerOrdenGuardado(clave) ?? []);

  useEffect(() => {
    setOrdenGuardado(leerOrdenGuardado(clave) ?? []);
  }, [clave]);

  const idsActuales = items.map(idDe);
  const ordenEfectivo = combinarOrden(ordenGuardado, idsActuales);

  const porId = new Map(items.map((item) => [idDe(item), item]));
  const ordenados = ordenEfectivo.map((id) => porId.get(id)).filter((item): item is T => item !== undefined);

  const mover = (idOrigen: string, idDestino: string) => {
    const nuevo = moverEnOrden(ordenEfectivo, idOrigen, idDestino);
    if (nuevo === ordenEfectivo) return;
    setOrdenGuardado(nuevo);
    guardarOrden(clave, nuevo);
  };

  return [ordenados, mover];
}
