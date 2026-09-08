import estilos from "./Cargando.module.css";

export function Cargando({ texto = "Cargando…", chico = false }: { texto?: string; chico?: boolean }) {
  return (
    <div className={`${estilos.cargando} ${chico ? estilos.chico : ""}`} role="status" aria-live="polite">
      <span className={estilos.punto} />
      <span>{texto}</span>
    </div>
  );
}

/** Bloque gris que ocupa el lugar de un panel mientras llegan los datos. */
export function Esqueleto({ alto = 120 }: { alto?: number }) {
  return <div className={estilos.esqueleto} style={{ height: alto }} aria-hidden="true" />;
}
