/* Cliente HTTP minimo. La sesion viaja en la cookie httpOnly; el frontend
   nunca ve el token. Un 401 en cualquier pedido avisa a la app para volver
   al login. */
import type { ErrorApiCuerpo } from "../tipos";

export const EVENTO_SESION_VENCIDA = "uboard:sesion-vencida";

export class ErrorApi extends Error {
  constructor(
    public estado: number,
    public cuerpo: ErrorApiCuerpo,
  ) {
    super(cuerpo.mensaje);
    this.name = "ErrorApi";
  }
}

interface OpcionesPedido extends Omit<RequestInit, "body"> {
  json?: unknown;
  body?: BodyInit;
}

export async function pedir<T>(ruta: string, opciones: OpcionesPedido = {}): Promise<T> {
  const { json, headers, ...resto } = opciones;
  const cabeceras = new Headers(headers);
  let cuerpo = resto.body;
  if (json !== undefined) {
    cabeceras.set("Content-Type", "application/json");
    cuerpo = JSON.stringify(json);
  }
  const respuesta = await fetch(ruta, { credentials: "same-origin", ...resto, headers: cabeceras, body: cuerpo });
  if (respuesta.status === 204) {
    return undefined as T;
  }
  const texto = await respuesta.text();
  let datos: unknown = null;
  if (texto) {
    try {
      datos = JSON.parse(texto);
    } catch {
      datos = { detail: texto };
    }
  }
  if (!respuesta.ok) {
    const crudo = (datos ?? {}) as Record<string, unknown>;
    const cuerpoError: ErrorApiCuerpo =
      typeof crudo.codigo === "string"
        ? (crudo as unknown as ErrorApiCuerpo)
        : { codigo: `HTTP-${respuesta.status}`, mensaje: describirFallo(crudo.detail, respuesta.statusText) };
    if (respuesta.status === 401) {
      window.dispatchEvent(new Event(EVENTO_SESION_VENCIDA));
    }
    throw new ErrorApi(respuesta.status, cuerpoError);
  }
  return datos as T;
}

function describirFallo(detalle: unknown, porDefecto: string): string {
  if (typeof detalle === "string") return detalle;
  if (Array.isArray(detalle)) {
    return detalle
      .map((error) => {
        const e = error as { loc?: unknown[]; msg?: string };
        return `${(e.loc ?? []).join(".")}: ${e.msg ?? ""}`;
      })
      .join("; ");
  }
  return porDefecto || "Algo salió mal.";
}

export function rutaWorkspace(workspaceId: number, sufijo = ""): string {
  return `/api/workspaces/${workspaceId}${sufijo}`;
}

export function mensajeDeError(error: unknown): string {
  if (error instanceof ErrorApi) {
    const partes = [error.cuerpo.mensaje];
    if (error.cuerpo.detalle) partes.push(`(${error.cuerpo.detalle})`);
    return partes.join(" ");
  }
  if (error instanceof Error) return error.message;
  return "Algo salió mal.";
}

export function codigoDeError(error: unknown): string | null {
  return error instanceof ErrorApi ? error.cuerpo.codigo : null;
}
