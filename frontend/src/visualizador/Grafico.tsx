import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Esqueleto } from "../compartido/componentes/Cargando";
import { SIN_DATO, etiquetaPeriodo, formatearMetrica } from "../compartido/formato";
import { opcionDeGrafico } from "../compartido/graficos/opciones";
import { useGrafico } from "../compartido/graficos/useGrafico";
import { useTema } from "../compartido/tema";
import type { FiltrosActivos, FiltroSpec, GraficoSalida, GraficoSpec } from "../tipos";
import estilos from "./Grafico.module.css";
import { parametroFiltros } from "./Tablero";

interface Props {
  workspaceId: number;
  grafico: GraficoSpec;
  filtros: string | null;
  alto: number;
  // Click-to-filter (paso A de la fase 4): si la dimension del grafico
  // coincide con el campo de un filtro de tipo "lista", clickear una barra
  // o porcion aplica ese filtro, igual que tildarlo en el chip.
  filtrosSpec: FiltroSpec[];
  filtrosActivos: FiltrosActivos;
  onCambiarFiltros: (filtros: FiltrosActivos) => void;
}

export function Grafico({ workspaceId, grafico, filtros, alto, filtrosSpec, filtrosActivos, onCambiarFiltros }: Props) {
  const [comoTabla, setComoTabla] = useState(false);
  const tema = useTema();
  const consulta = useQuery({
    queryKey: ["grafico", workspaceId, grafico.id, filtros],
    queryFn: () => pedir<GraficoSalida>(rutaWorkspace(workspaceId, `/dashboard/graficos/${grafico.id}${parametroFiltros(filtros)}`)),
    placeholderData: (anterior) => anterior,
  });
  const opcion = useMemo(() => (consulta.data && !comoTabla ? opcionDeGrafico(consulta.data, tema) : null), [consulta.data, tema, comoTabla]);
  const datos = consulta.data;

  // Un filtro de tipo "lista" sobre el mismo campo que la dimension: ahi el
  // grafico se puede clickear. Los de rango de fecha quedan afuera (un
  // click no alcanza para armar un rango).
  const filtroClickeable = filtrosSpec.find((filtro) => filtro.campo === grafico.dimension && filtro.tipo === "lista");
  const alClickear = (dataIndex: number) => {
    if (!filtroClickeable || !datos) return;
    const fila = datos.filas[dataIndex];
    if (!fila || fila[0] === null || fila[0] === undefined) return;
    const valor = String(fila[0]);
    const seleccionActual = filtrosActivos[filtroClickeable.id];
    const yaEsElUnico = Array.isArray(seleccionActual) && seleccionActual.length === 1 && String(seleccionActual[0]) === valor;
    onCambiarFiltros({ ...filtrosActivos, [filtroClickeable.id]: yaEsElUnico ? [] : [valor] });
  };
  const contenedor = useGrafico(opcion, filtroClickeable ? alClickear : undefined);
  return (
    <figure className={`${estilos.grafico} ${consulta.isPlaceholderData ? estilos.atenuado : ""}`}>
      <figcaption className={estilos.cabecera}>
        <div>
          <h3 className={estilos.titulo}>{datos?.titulo ?? grafico.titulo ?? grafico.metrica}</h3>
          {datos && <span className="mudo">{datos.metrica.nombre}</span>}
          {filtroClickeable && !comoTabla && <span className={`mudo ${estilos.pista}`}>Clickeá para filtrar por {filtroClickeable.etiqueta ?? filtroClickeable.campo}</span>}
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
      <div
        ref={contenedor}
        className={`${estilos.lienzo} ${filtroClickeable ? estilos.clickeable : ""}`}
        style={{ height: datos && datos.filas.length > 0 && !comoTabla ? alto : 0 }}
        role="img"
        aria-label={datos?.titulo}
      />
    </figure>
  );
}
