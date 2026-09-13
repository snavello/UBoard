/* Diagrama del modelo semantico, tipo DER: cada entidad como una caja con
   sus campos, las relaciones como conectores con notacion "pata de gallo"
   (crow's foot) — el lado "muchos" abre en tres puntas, el lado "uno" lleva
   dos marcas perpendiculares, igual que un diagrama entidad-relacion de
   toda la vida. El layout es puro (`diagramaLayout.ts`), sin libreria de
   grafos: el modelo nunca tiene ciclos de relaciones (lo exige la
   validacion), asi que alcanza un BFS por capas. */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import type { Campo, ModeloSemantico, VersionCompleta } from "../tipos";
import { ANCHO_CAJA, calcularLayout, type Conector, type LadoCardinalidad } from "./diagramaLayout";
import estilos from "./Diagrama.module.css";

const MARGEN = 24;

function trazoConector(conector: Conector): string {
  const { desde, hacia } = conector;
  const alcance = Math.max(30, Math.min(60, Math.abs(hacia.x - desde.x) * 0.4));
  const c1x = desde.x + alcance * desde.direccion;
  const c2x = hacia.x + alcance * hacia.direccion;
  return `M ${desde.x} ${desde.y} C ${c1x} ${desde.y}, ${c2x} ${hacia.y}, ${hacia.x} ${hacia.y}`;
}

function trazoMarcador(x: number, y: number, direccion: 1 | -1, lado: LadoCardinalidad): string {
  if (lado === "uno") {
    const t1 = x + 5 * direccion;
    const t2 = x + 11 * direccion;
    return `M ${t1} ${y - 6} L ${t1} ${y + 6} M ${t2} ${y - 6} L ${t2} ${y + 6}`;
  }
  const punta = x + 14 * direccion;
  return `M ${x} ${y} L ${punta} ${y - 7} M ${x} ${y} L ${punta} ${y} M ${x} ${y} L ${punta} ${y + 7}`;
}

function claseCampo(campo: Campo): string {
  if (campo.estado === "rechazada") return estilos.campoRechazado;
  if (campo.estado === "propuesta") return estilos.campoPropuesto;
  return estilos.campoConfirmado;
}

interface Props {
  workspaceId: number;
}

export function Diagrama({ workspaceId }: Props) {
  const consulta = useQuery({
    queryKey: ["modelo", workspaceId],
    queryFn: () => pedir<VersionCompleta>(rutaWorkspace(workspaceId, "/modelo")),
    retry: false,
  });

  const modelo = consulta.data?.contenido as unknown as ModeloSemantico | undefined;
  const layout = useMemo(() => (modelo ? calcularLayout(modelo) : null), [modelo]);

  if (consulta.isPending) return <Cargando texto="Armando el diagrama…" />;
  if (consulta.isError) return <AvisoError error={consulta.error} titulo="No pudimos abrir el modelo" />;
  if (!layout || layout.cajas.length === 0) return <p className="mudo">Todavía no hay un modelo cargado.</p>;

  return (
    <div className={estilos.envoltorio}>
      <p className={`mudo ${estilos.leyenda}`}>
        <span className={estilos.chip}>
          <svg width="20" height="14" aria-hidden="true">
            <path d="M 2 7 L 16 3 M 2 7 L 16 7 M 2 7 L 16 11" />
          </svg>
          lado "muchos"
        </span>
        <span className={estilos.chip}>
          <svg width="20" height="14" aria-hidden="true">
            <path d="M 6 1 L 6 13 M 12 1 L 12 13" />
          </svg>
          lado "uno" (clave primaria)
        </span>
      </p>
      <div className={estilos.lienzo}>
        <svg
          width={layout.ancho + MARGEN * 2}
          height={layout.alto + MARGEN * 2}
          viewBox={`${-MARGEN} ${-MARGEN} ${layout.ancho + MARGEN * 2} ${layout.alto + MARGEN * 2}`}
          role="img"
          aria-label="Diagrama entidad-relación del modelo"
        >
          <g className={estilos.conectores}>
            {layout.conectores.map((conector) => (
              <g key={conector.relacion.id}>
                <path d={trazoConector(conector)} className={estilos.trazo} />
                <path d={trazoMarcador(conector.desde.x, conector.desde.y, conector.desde.direccion, conector.desde.lado)} className={estilos.marcador} />
                <path d={trazoMarcador(conector.hacia.x, conector.hacia.y, conector.hacia.direccion, conector.hacia.lado)} className={estilos.marcador} />
              </g>
            ))}
          </g>
          {layout.cajas.map(({ entidad, x, y, alto, filas }) => (
            <g key={entidad.id} transform={`translate(${x}, ${y})`}>
              <rect className={estilos.caja} width={ANCHO_CAJA} height={alto} rx={8} />
              <rect className={`${estilos.cabecera} ${entidad.tipo === "hechos" ? estilos.cabeceraHechos : estilos.cabeceraDimension}`} width={ANCHO_CAJA} height={40} rx={8} />
              <rect className={`${entidad.tipo === "hechos" ? estilos.cabeceraHechos : estilos.cabeceraDimension}`} x={0} y={24} width={ANCHO_CAJA} height={16} />
              <text x={12} y={19} className={estilos.tituloEntidad}>
                {entidad.nombre}
              </text>
              <text x={ANCHO_CAJA - 10} y={33} textAnchor="end" className={estilos.tipoEntidad}>
                {entidad.tipo === "hechos" ? "Hechos" : "Dimensión"}
              </text>
              <line x1={0} y1={40} x2={ANCHO_CAJA} y2={40} className={estilos.divisor} />
              {filas.map(({ campo, esClave, y: yFila }) => (
                <g key={campo.id} className={claseCampo(campo)}>
                  {esClave && (
                    <circle cx={14} cy={yFila} r={3} className={estilos.puntoClave} />
                  )}
                  <text x={esClave ? 24 : 12} y={yFila + 4} className={estilos.nombreCampo}>
                    {campo.nombre}
                  </text>
                  <text x={ANCHO_CAJA - 10} y={yFila + 4} textAnchor="end" className={estilos.tipoCampo}>
                    {campo.tipo_semantico}
                  </text>
                </g>
              ))}
            </g>
          ))}
        </svg>
      </div>
    </div>
  );
}
