import type { ControlesArrastre } from "../ordenPersonal";
import estilos from "./Pestanias.module.css";

export interface Pestania {
  id: string;
  titulo: string;
  extra?: string;
}

interface Props {
  pestanias: Pestania[];
  activa: string;
  onCambiar: (id: string) => void;
  derecha?: React.ReactNode;
  // Orden personal por arrastre (fase 4): opcional, para no afectar a los
  // demas usos de este componente (las pestanias fijas de Modelo). Una
  // pestania no tiene interaccion propia adentro, asi que el boton entero
  // sirve de agarradero y de contenedor a la vez.
  arrastre?: ControlesArrastre;
}

export function Pestanias({ pestanias, activa, onCambiar, derecha, arrastre }: Props) {
  return (
    <div className={estilos.barra} role="tablist">
      {pestanias.map((pestania) => {
        const lado = arrastre?.ladoDestino(pestania.id) ?? null;
        return (
          <button
            key={pestania.id}
            type="button"
            role="tab"
            aria-selected={pestania.id === activa}
            className={`${estilos.pestania} ${pestania.id === activa ? estilos.activa : ""} ${lado === "antes" ? estilos.destinoAntes : lado === "despues" ? estilos.destinoDespues : ""}`}
            onClick={() => onCambiar(pestania.id)}
            {...(arrastre ? { ...arrastre.handleProps(pestania.id), ...arrastre.contenedorProps(pestania.id) } : {})}
          >
            {pestania.titulo}
            {pestania.extra && <span className={estilos.extra}>{pestania.extra}</span>}
          </button>
        );
      })}
      {derecha && <div className={estilos.derecha}>{derecha}</div>}
    </div>
  );
}
