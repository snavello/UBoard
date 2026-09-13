/* Geometria pura de "donde soltar" (drag and drop nativo del navegador,
   sin libreria). No sabe de listas, ids ni React: solo dice si un punto
   esta mas cerca de la mitad "antes" (arriba-izquierda) o "despues"
   (abajo-derecha) de un rectangulo, en el sentido de lectura. Sirve para
   filas (pestanias), grillas de 2 columnas (KPIs, graficos) y bloques
   sueltos por igual, sin necesitar saber la orientacion de cada layout:
   por eso usa las dos coordenadas a la vez (arriba de la diagonal =
   antes, abajo = despues) en vez de mirar solo X o solo Y. */
export function ladoDeSoltar(clientX: number, clientY: number, rect: { left: number; top: number; width: number; height: number }): "antes" | "despues" {
  if (rect.width <= 0 || rect.height <= 0) return "antes";
  const relX = (clientX - rect.left) / rect.width;
  const relY = (clientY - rect.top) / rect.height;
  return relX + relY > 1 ? "despues" : "antes";
}
