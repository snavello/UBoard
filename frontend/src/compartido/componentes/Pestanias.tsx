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
}

export function Pestanias({ pestanias, activa, onCambiar, derecha }: Props) {
  return (
    <div className={estilos.barra} role="tablist">
      {pestanias.map((pestania) => (
        <button
          key={pestania.id}
          type="button"
          role="tab"
          aria-selected={pestania.id === activa}
          className={`${estilos.pestania} ${pestania.id === activa ? estilos.activa : ""}`}
          onClick={() => onCambiar(pestania.id)}
        >
          {pestania.titulo}
          {pestania.extra && <span className={estilos.extra}>{pestania.extra}</span>}
        </button>
      ))}
      {derecha && <div className={estilos.derecha}>{derecha}</div>}
    </div>
  );
}
