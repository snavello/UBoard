/* Agarradero visible para arrastrar y reordenar (fase 4): un SVG propio en
   vez de un caracter Unicode (el "⠿" original quedaba casi invisible con
   Source Sans 3 - Sd lo reporto de entrada), asi el tamaño y el contraste
   no dependen de que fuente ande instalada. La "pastilla" con borde lo hace
   reconocible como control, no solo como una decoracion. */
import estilos from "./AgarraderoArrastre.module.css";

interface Props {
  arrastrar: {
    draggable: true;
    onDragStart: (evento: React.DragEvent) => void;
    onDragEnd: () => void;
  };
}

export function AgarraderoArrastre({ arrastrar }: Props) {
  return (
    <span className={estilos.agarradero} {...arrastrar} title="Arrastrar para reordenar" aria-hidden="true">
      <svg width="10" height="16" viewBox="0 0 10 16">
        <circle cx="3" cy="3" r="1.4" />
        <circle cx="7" cy="3" r="1.4" />
        <circle cx="3" cy="8" r="1.4" />
        <circle cx="7" cy="8" r="1.4" />
        <circle cx="3" cy="13" r="1.4" />
        <circle cx="7" cy="13" r="1.4" />
      </svg>
    </span>
  );
}
