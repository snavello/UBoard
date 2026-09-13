import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { useArrastreDeOrden } from "../compartido/arrastre";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Esqueleto } from "../compartido/componentes/Cargando";
import { formatearMetrica } from "../compartido/formato";
import { useOrdenPersonal } from "../compartido/ordenPersonal";
import type { KpiSalida, SpecDashboard } from "../tipos";
import estilos from "./Kpis.module.css";
import { parametroFiltros } from "./Tablero";

interface Props {
  workspaceId: number;
  spec: SpecDashboard;
  filtros: string | null;
}

export function Kpis({ workspaceId, spec, filtros }: Props) {
  const consulta = useQuery({
    queryKey: ["kpis", workspaceId, filtros],
    queryFn: () => pedir<KpiSalida[]>(rutaWorkspace(workspaceId, `/dashboard/kpis${parametroFiltros(filtros)}`)),
    placeholderData: (anterior) => anterior,
  });

  if (consulta.isPending) {
    return (
      <div className={estilos.kpis}>
        <Esqueleto alto={110} />
        <Esqueleto alto={140} />
      </div>
    );
  }
  if (consulta.isError) return <AvisoError error={consulta.error} titulo="No pudimos calcular los indicadores" />;
  if (!consulta.data.length) return null;

  return <KpisOrdenables workspaceId={workspaceId} spec={spec} kpis={consulta.data} atenuado={consulta.isPlaceholderData} />;
}

function KpisOrdenables({ workspaceId, spec, kpis, atenuado }: { workspaceId: number; spec: SpecDashboard; kpis: KpiSalida[]; atenuado: boolean }) {
  // El orden es una preferencia personal (arrastrar y soltar, guardada en
  // este navegador): el primero de la lista sigue siendo el protagonista,
  // así que arrastrar otro KPI al principio lo promueve a cifra grande.
  const [ordenados, mover] = useOrdenPersonal("kpis", workspaceId, kpis, (kpi) => kpi.id);
  const arrastre = useArrastreDeOrden(mover);
  const [protagonista, ...resto] = ordenados;

  return (
    <div className={`${estilos.kpis} ${atenuado ? estilos.atenuado : ""}`}>
      <div
        className={`${estilos.protagonista} ${arrastre.esDestino(protagonista.id) ? estilos.destinoArrastre : ""}`}
        {...arrastre.contenedorProps(protagonista.id)}
      >
        <span className={estilos.agarradero} {...arrastre.handleProps(protagonista.id)} title="Arrastrar para reordenar" aria-hidden="true">
          ⠿
        </span>
        <span className={estilos.etiqueta}>{protagonista.titulo}</span>
        <span className={`${estilos.cifraGrande}`}>{formatearMetrica(protagonista.valor, protagonista.formato)}</span>
        {spec.filtros.length > 0 && <span className="mudo">con los filtros activos</span>}
      </div>
      {resto.length > 0 && (
        <dl className={estilos.grilla}>
          {resto.map((kpi) => (
            <div
              key={kpi.id}
              className={`${estilos.kpi} ${arrastre.esDestino(kpi.id) ? estilos.destinoArrastre : ""}`}
              {...arrastre.contenedorProps(kpi.id)}
            >
              <span className={estilos.agarradero} {...arrastre.handleProps(kpi.id)} title="Arrastrar para reordenar" aria-hidden="true">
                ⠿
              </span>
              <dt className={estilos.etiqueta}>{kpi.titulo}</dt>
              <dd className={estilos.cifra}>{formatearMetrica(kpi.valor, kpi.formato)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
