import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Esqueleto } from "../compartido/componentes/Cargando";
import { SIN_DATO, etiquetaPeriodo, formatearMetrica } from "../compartido/formato";
import { opcionDeGrafico } from "../compartido/graficos/opciones";
import { useGrafico } from "../compartido/graficos/useGrafico";
import { useTema } from "../compartido/tema";
import type { GraficoSalida, GraficoSpec } from "../tipos";
import estilos from "./Grafico.module.css";
import { parametroFiltros } from "./Tablero";

interface Props {
  workspaceId: number;
  grafico: GraficoSpec;
  filtros: string | null;
  alto: number;
}

export function Grafico({ workspaceId, grafico, filtros, alto }: Props) {
  const [comoTabla, setComoTabla] = useState(false);
  const tema = useTema();
  const consulta = useQuery({
    queryKey: ["grafico", workspaceId, grafico.id, filtros],
    queryFn: () => pedir<GraficoSalida>(rutaWorkspace(workspaceId, `/dashboard/graficos/${grafico.id}${parametroFiltros(filtros)}`)),
    placeholderData: (anterior) => anterior,
  });
  const opcion = useMemo(() => (consulta.data && !comoTabla ? opcionDeGrafico(consulta.data, tema) : null), [consulta.data, tema, comoTabla]);
  const contenedor = useGrafico(opcion);

  const datos = consulta.data;
  return (
    <figure className={`${estilos.grafico} ${consulta.isPlaceholderData ? estilos.atenuado : ""}`}>
      <figcaption className={estilos.cabecera}>
        <div>
          <h3 className={estilos.titulo}>{datos?.titulo ?? grafico.titulo ?? grafico.metrica}</h3>
          {datos && <span className="mudo">{datos.metrica.nombre}</span>}
        </div>
        {datos && datos.filas.length > 0 && (
          <button type="button" className="boton boton--texto boton--chico" onClick={() => setComoTabla((valor) => !valor)}>
            {comoTabla ? "Ver gráfico" : "Ver tabla"}
          </button>
        )}
      </figcaption>

      {consulta.isPending && <Esqueleto alto={alto} />}
      {consulta.isError && <AvisoError error={consulta.error} />}
      {datos && datos.filas.length === 0 && (
        <p className={`${estilos.vacio} mudo`} style={{ height: alto }}>
          Sin datos para los filtros activos.
        </p>
      )}
      {datos && datos.filas.length > 0 && comoTabla && (
        <div className={estilos.tablaEnvoltorio} style={{ maxHeight: alto }}>
          <table className="tabla">
            <thead>
              <tr>
                <th>{datos.dimension.nombre}</th>
                <th className="numero">{datos.metrica.nombre}</th>
              </tr>
            </thead>
            <tbody>
              {datos.filas.map((fila, indice) => (
                <tr key={indice}>
                  <td>{fila[0] === null ? SIN_DATO : datos.dimension.tipo === "fecha" ? etiquetaPeriodo(fila[0], datos.dimension.granularidad) : String(fila[0])}</td>
                  <td className="numero">{formatearMetrica(fila[1], datos.metrica.formato)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div ref={contenedor} className={estilos.lienzo} style={{ height: datos && datos.filas.length > 0 && !comoTabla ? alto : 0 }} role="img" aria-label={datos?.titulo} />
    </figure>
  );
}
