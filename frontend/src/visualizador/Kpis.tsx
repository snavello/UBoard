import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Esqueleto } from "../compartido/componentes/Cargando";
import { formatearMetrica } from "../compartido/formato";
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

  const [protagonista, ...resto] = consulta.data;
  const atenuado = consulta.isPlaceholderData ? estilos.atenuado : "";

  return (
    <div className={`${estilos.kpis} ${atenuado}`}>
      <div className={estilos.protagonista}>
        <span className={estilos.etiqueta}>{protagonista.titulo}</span>
        <span className={`${estilos.cifraGrande}`}>{formatearMetrica(protagonista.valor, protagonista.formato)}</span>
        {spec.filtros.length > 0 && <span className="mudo">con los filtros activos</span>}
      </div>
      {resto.length > 0 && (
        <dl className={estilos.grilla}>
          {resto.map((kpi) => (
            <div key={kpi.id} className={estilos.kpi}>
              <dt className={estilos.etiqueta}>{kpi.titulo}</dt>
              <dd className={estilos.cifra}>{formatearMetrica(kpi.valor, kpi.formato)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}
