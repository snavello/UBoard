/* La planilla de detalle: pestanias por entidad, tabla ordenable y paginada,
   con los mismos filtros que el resto del tablero. */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { useArrastreDeOrden } from "../compartido/arrastre";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Paginador } from "../compartido/componentes/Paginador";
import { Pestanias } from "../compartido/componentes/Pestanias";
import { esNumerico, formatearCelda } from "../compartido/formato";
import { useOrdenPersonal } from "../compartido/ordenPersonal";
import type { ExploradorSalida, PestaniaSpec, SpecDashboard } from "../tipos";
import estilos from "./Explorador.module.css";

interface Props {
  workspaceId: number;
  spec: SpecDashboard;
  filtros: string | null;
}

function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1).replace(/_/g, " ");
}

export function Explorador({ workspaceId, spec, filtros }: Props) {
  // El orden de las pestanias es una preferencia personal (arrastrar y
  // soltar, guardada en este navegador), no la estructura del spec.
  const [pestanias, moverPestania] = useOrdenPersonal("pestanias", workspaceId, spec.explorador.pestanias, (pestania: PestaniaSpec) => pestania.entidad);
  const arrastrePestanias = useArrastreDeOrden(moverPestania);
  const [activa, setActiva] = useState(pestanias[0]?.entidad ?? "");
  const [pagina, setPagina] = useState(1);
  const [orden, setOrden] = useState<{ por: string; direccion: "asc" | "desc" } | null>(null);

  useEffect(() => {
    setPagina(1);
  }, [filtros, activa, orden]);

  const parametros = new URLSearchParams();
  if (filtros) parametros.set("filtros", filtros);
  parametros.set("pagina", String(pagina));
  if (orden) {
    parametros.set("orden", orden.por);
    parametros.set("direccion", orden.direccion);
  }

  const consulta = useQuery({
    queryKey: ["explorador", workspaceId, activa, filtros, pagina, orden],
    queryFn: () => pedir<ExploradorSalida>(rutaWorkspace(workspaceId, `/dashboard/explorador/${activa}?${parametros}`)),
    enabled: Boolean(activa),
    placeholderData: (anterior) => anterior,
  });

  const cambiarPestania = (entidad: string) => {
    setActiva(entidad);
    setOrden(null);
  };

  const ordenarPor = (alias: string) => {
    setOrden((actual) => (actual?.por === alias ? { por: alias, direccion: actual.direccion === "asc" ? "desc" : "asc" } : { por: alias, direccion: "asc" }));
  };

  const datos = consulta.data;
  const columnas = datos?.columnas.filter((columna) => !columna.oculta) ?? [];
  const indicesVisibles = datos?.columnas.map((columna, indice) => (columna.oculta ? -1 : indice)).filter((indice) => indice >= 0) ?? [];

  return (
    <div className={estilos.explorador}>
      <Pestanias
        pestanias={pestanias.map((pestania) => ({ id: pestania.entidad, titulo: pestania.titulo ?? capitalizar(pestania.entidad) }))}
        activa={activa}
        onCambiar={cambiarPestania}
        derecha={datos ? `${datos.total.toLocaleString("es-AR")} filas` : undefined}
        arrastre={arrastrePestanias}
      />
      {consulta.isPending && <Cargando texto="Buscando filas…" />}
      {consulta.isError && <AvisoError error={consulta.error} titulo="No pudimos cargar el detalle" />}
      {datos && (
        <div className={`${estilos.tablaEnvoltorio} ${consulta.isPlaceholderData ? estilos.atenuado : ""}`}>
          <table className="tabla">
            <thead>
              <tr>
                {columnas.map((columna) => {
                  const numerica = columna.clase === "metrica" || esNumerico(columna.tipo);
                  const ordenada = orden?.por === columna.alias;
                  return (
                    <th key={columna.alias} className={numerica ? "numero" : undefined} aria-sort={ordenada ? (orden?.direccion === "asc" ? "ascending" : "descending") : "none"}>
                      <button type="button" className={`${estilos.ordenar} ${ordenada ? estilos.ordenada : ""}`} onClick={() => ordenarPor(columna.alias)}>
                        {columna.titulo}
                        <span aria-hidden="true">{ordenada ? (orden?.direccion === "asc" ? " ↑" : " ↓") : ""}</span>
                      </button>
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {datos.filas.map((fila, indiceFila) => (
                <tr key={indiceFila}>
                  {indicesVisibles.map((indice, posicion) => {
                    const columna = columnas[posicion];
                    const numerica = columna.clase === "metrica" || esNumerico(columna.tipo);
                    return (
                      <td key={columna.alias} className={numerica ? "numero" : undefined}>
                        {formatearCelda(fila[indice], columna.tipo, columna.formato)}
                      </td>
                    );
                  })}
                </tr>
              ))}
              {datos.filas.length === 0 && (
                <tr>
                  <td colSpan={columnas.length} className="mudo">
                    Sin filas para los filtros activos.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      {datos && <Paginador pagina={datos.pagina} tamanio={datos.tamanio} total={datos.total} onCambiar={setPagina} />}
    </div>
  );
}
