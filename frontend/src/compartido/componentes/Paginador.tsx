import { formatearNumero } from "../formato";
import estilos from "./Paginador.module.css";

interface Props {
  pagina: number;
  tamanio: number;
  total: number;
  onCambiar: (pagina: number) => void;
  sustantivo?: string;
}

export function Paginador({ pagina, tamanio, total, onCambiar, sustantivo = "filas" }: Props) {
  const paginas = Math.max(1, Math.ceil(total / tamanio));
  return (
    <div className={estilos.paginador}>
      <span className="mudo">
        {formatearNumero(total, 0)} {sustantivo} · página {pagina} de {paginas}
      </span>
      <div className={estilos.botones}>
        <button type="button" className="boton boton--chico" disabled={pagina <= 1} onClick={() => onCambiar(pagina - 1)} aria-label="Página anterior">
          ‹
        </button>
        <button type="button" className="boton boton--chico" disabled={pagina >= paginas} onClick={() => onCambiar(pagina + 1)} aria-label="Página siguiente">
          ›
        </button>
      </div>
    </div>
  );
}
