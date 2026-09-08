import type { ReactNode } from "react";

import type { ErrorValidacion } from "../../tipos";
import { codigoDeError, mensajeDeError } from "../api";
import estilos from "./Aviso.module.css";

interface Props {
  tipo?: "error" | "advertencia" | "info" | "exito";
  titulo?: string;
  children?: ReactNode;
}

export function Aviso({ tipo = "info", titulo, children }: Props) {
  return (
    <div className={`${estilos.aviso} ${estilos[tipo]}`} role={tipo === "error" ? "alert" : "status"}>
      {titulo && <strong className={estilos.titulo}>{titulo}</strong>}
      <div>{children}</div>
    </div>
  );
}

/** Un error de la API, con su codigo visible para encontrarlo en el backend. */
export function AvisoError({ error, titulo }: { error: unknown; titulo?: string }) {
  const codigo = codigoDeError(error);
  return (
    <Aviso tipo="error" titulo={titulo}>
      {mensajeDeError(error)}
      {codigo && <span className={`${estilos.codigo} codigo`}>{codigo}</span>}
    </Aviso>
  );
}

export function ListaErrores({ errores }: { errores: ErrorValidacion[] }) {
  if (!errores.length) return null;
  return (
    <ul className={estilos.lista}>
      {errores.map((error, indice) => (
        <li key={`${error.codigo}-${error.ubicacion}-${indice}`}>
          <span className="codigo">{error.ubicacion}</span> {error.mensaje}{" "}
          <span className={`${estilos.codigo} codigo`}>{error.codigo}</span>
        </li>
      ))}
    </ul>
  );
}
