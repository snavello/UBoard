/* Formato es-AR: "$ 1.234,56", "12/03/2026", "ene 2026". Los valores llegan
   crudos de la API (numeros, fechas ISO); aca se convierten en texto. */
import type { Formato } from "../tipos";

const LOCALE = "es-AR";
const MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

export const SIN_DATO = "(sin dato)";

export function formatearNumero(valor: number, decimales: number): string {
  return valor.toLocaleString(LOCALE, { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
}

/** Un numero segun el formato de su metrica. */
export function formatearMetrica(valor: number | null | undefined, formato: Formato | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  switch (formato) {
    case "moneda":
      return `$ ${formatearNumero(valor, Math.abs(valor) >= 10_000 ? 0 : 2)}`;
    case "entero":
      return formatearNumero(valor, 0);
    case "porcentaje":
      return `${formatearNumero(valor * 100, 1)} %`;
    default:
      return formatearNumero(valor, Number.isInteger(valor) ? 0 : 2);
  }
}

/** Version corta para ejes: 1,2 k · 4,8 M · 48,3 M. */
export function formatearCompacto(valor: number, formato?: Formato | null): string {
  const prefijo = formato === "moneda" ? "$ " : "";
  const absoluto = Math.abs(valor);
  if (formato === "porcentaje") return `${formatearNumero(valor * 100, 0)} %`;
  if (absoluto >= 1_000_000_000) return `${prefijo}${formatearNumero(valor / 1_000_000_000, 1)} mil M`;
  if (absoluto >= 1_000_000) return `${prefijo}${formatearNumero(valor / 1_000_000, 1)} M`;
  if (absoluto >= 10_000) return `${prefijo}${formatearNumero(valor / 1_000, 0)} k`;
  return `${prefijo}${formatearNumero(valor, absoluto >= 100 || Number.isInteger(valor) ? 0 : 1)}`;
}

function partesDeFecha(iso: string): { anio: number; mes: number; dia: number } | null {
  const coincidencia = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!coincidencia) return null;
  return { anio: Number(coincidencia[1]), mes: Number(coincidencia[2]), dia: Number(coincidencia[3]) };
}

export function formatearFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  const partes = partesDeFecha(iso);
  if (!partes) return iso;
  const dia = String(partes.dia).padStart(2, "0");
  const mes = String(partes.mes).padStart(2, "0");
  const hora = /T(\d{2}:\d{2})/.exec(iso);
  return hora ? `${dia}/${mes}/${partes.anio} ${hora[1]}` : `${dia}/${mes}/${partes.anio}`;
}

/** Etiqueta de un periodo segun la granularidad: "ene 2026", "T1 2026", "2026", "12/01". */
export function etiquetaPeriodo(iso: unknown, granularidad: string | null | undefined): string {
  if (iso === null || iso === undefined) return SIN_DATO;
  if (typeof iso !== "string") return String(iso);
  const partes = partesDeFecha(iso);
  if (!partes) return iso;
  switch (granularidad) {
    case "anio":
      return String(partes.anio);
    case "trimestre":
      return `T${Math.ceil(partes.mes / 3)} ${partes.anio}`;
    case "mes":
      return `${MESES_CORTOS[partes.mes - 1]} ${partes.anio}`;
    case "semana":
    case "dia":
      return `${String(partes.dia).padStart(2, "0")}/${String(partes.mes).padStart(2, "0")}/${String(partes.anio).slice(2)}`;
    default:
      return formatearFecha(iso);
  }
}

/** Una celda cualquiera del explorador o de una muestra. */
export function formatearCelda(valor: unknown, tipo: string, formato?: Formato | null): string {
  if (valor === null || valor === undefined) return "—";
  if (formato && typeof valor === "number") return formatearMetrica(valor, formato);
  switch (tipo) {
    case "fecha":
    case "fecha_hora":
      return formatearFecha(String(valor));
    case "booleano":
      return valor ? "Sí" : "No";
    case "entero":
      return typeof valor === "number" ? formatearNumero(valor, 0) : String(valor);
    case "decimal":
      return typeof valor === "number" ? formatearNumero(valor, 2) : String(valor);
    default:
      return String(valor);
  }
}

export function esNumerico(tipo: string): boolean {
  return tipo === "entero" || tipo === "decimal";
}

/** Fecha ISO (aaaa-mm-dd) de hoy en hora local. */
export function hoyIso(): string {
  const hoy = new Date();
  return `${hoy.getFullYear()}-${String(hoy.getMonth() + 1).padStart(2, "0")}-${String(hoy.getDate()).padStart(2, "0")}`;
}
