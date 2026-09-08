/* Paleta de series para los graficos. Validada con validate_palette.js del
   skill dataviz (orden fijo, separacion para daltonismo, contraste) sobre las
   superficies clara (#fdfcf9) y oscura (#1a1a19). El ORDEN es parte de la
   validacion: no reordenar. Con mas de 8 categorias, agrupar en "Otros". */
export const SERIES_CLARO = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"];
export const SERIES_OSCURO = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"];

/* Color de una serie unica (linea, barras): el acento del sistema, para que
   el grafico sea de la misma familia que los botones y las selecciones. */
export const SERIE_UNICA_CLARO = "#4a3aa7";
export const SERIE_UNICA_OSCURO = "#9085e9";

export function series(modoOscuro: boolean): string[] {
  return modoOscuro ? SERIES_OSCURO : SERIES_CLARO;
}

export function serieUnica(modoOscuro: boolean): string {
  return modoOscuro ? SERIE_UNICA_OSCURO : SERIE_UNICA_CLARO;
}
