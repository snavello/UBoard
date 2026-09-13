/* El dashboard: cabecera editorial, filtros como chips, cifra protagonista,
   graficos en orden de lectura y la planilla de detalle (explorador) debajo.
   No sabe de negocio: renderiza el spec que devuelve la API. */
import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";

import { Chat } from "../asistente/Chat";
import { codigoDeError, pedir, rutaWorkspace } from "../compartido/api";
import { Aviso, AvisoError, ListaErrores } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Marco } from "../compartido/componentes/Marco";
import { escribirFiltros, leerFiltros, serializarFiltros } from "../compartido/filtrosUrl";
import { useSesion } from "../compartido/sesion";
import type { DashboardSalida, FiltrosActivos } from "../tipos";
import { Explorador } from "./Explorador";
import { Filtros } from "./Filtros";
import { Grafico } from "./Grafico";
import { Kpis } from "./Kpis";
import estilos from "./Tablero.module.css";

export function parametroFiltros(serializados: string | null): string {
  return serializados ? `?filtros=${encodeURIComponent(serializados)}` : "";
}

export function Tablero() {
  const { usuario } = useSesion();
  const workspaceId = usuario?.workspace_id ?? 0;
  const [parametros, setParametros] = useSearchParams();
  const filtros = useMemo(() => leerFiltros(parametros), [parametros]);
  const filtrosSerializados = serializarFiltros(filtros);

  const dashboard = useQuery({
    queryKey: ["dashboard", workspaceId],
    queryFn: () => pedir<DashboardSalida>(rutaWorkspace(workspaceId, "/dashboard")),
    retry: false,
  });

  const cambiarFiltros = (nuevos: FiltrosActivos) => {
    setParametros(escribirFiltros(parametros, nuevos), { replace: true });
  };

  if (dashboard.isPending) {
    return (
      <Marco titulo="Tablero">
        <Cargando texto="Armando el tablero…" />
      </Marco>
    );
  }

  if (dashboard.isError) {
    const sinDashboard = codigoDeError(dashboard.error) === "E-SPEC-02";
    return (
      <Marco titulo="Tablero">
        {sinDashboard ? (
          <Aviso tipo="info" titulo="Todavía no hay un tablero">
            {usuario?.rol === "constructor" ? (
              <>
                Subí tus archivos en <Link to="/fuentes">Fuentes</Link>, cargá el modelo y el dashboard en <Link to="/modelo">Modelo</Link>, y
                volvé acá.
              </>
            ) : (
              "Quien construye el tablero todavía no lo publicó. Volvé más tarde."
            )}
          </Aviso>
        ) : (
          <AvisoError error={dashboard.error} titulo="No pudimos abrir el tablero" />
        )}
      </Marco>
    );
  }

  const spec = dashboard.data.contenido;
  const graficoPrincipal = spec.graficos[0];
  const graficosSecundarios = spec.graficos.slice(1);

  return (
    <Marco
      titulo={spec.titulo ?? "Tablero"}
      acciones={
        <>
          <Filtros workspaceId={workspaceId} spec={spec} filtros={filtros} onCambiar={cambiarFiltros} />
          <Chat
            variante="inline"
            filtrosActivos={filtros}
            onAplicarFiltro={(filtroId, valor) => cambiarFiltros({ ...filtros, [filtroId]: valor })}
          />
        </>
      }
    >
      {dashboard.data.advertencias.length > 0 && (
        <Aviso tipo="advertencia" titulo="El modelo cambió después de armar este tablero">
          Algunos paneles ya no cierran con el modelo actual. Quien construye tiene que revisar el dashboard.
          <ListaErrores errores={dashboard.data.advertencias} />
        </Aviso>
      )}

      <div className={estilos.cuerpo}>
        <aside className={estilos.columnaCifras}>
          <Kpis workspaceId={workspaceId} spec={spec} filtros={filtrosSerializados} />
        </aside>
        <section className={estilos.columnaGraficos} aria-label="Gráficos">
          {graficoPrincipal && (
            <Grafico
              workspaceId={workspaceId}
              grafico={graficoPrincipal}
              filtros={filtrosSerializados}
              alto={260}
              filtrosSpec={spec.filtros}
              filtrosActivos={filtros}
              onCambiarFiltros={cambiarFiltros}
            />
          )}
          {graficosSecundarios.length > 0 && (
            <div className={estilos.grilla}>
              {graficosSecundarios.map((grafico) => (
                <Grafico
                  key={grafico.id}
                  workspaceId={workspaceId}
                  grafico={grafico}
                  filtros={filtrosSerializados}
                  alto={220}
                  filtrosSpec={spec.filtros}
                  filtrosActivos={filtros}
                  onCambiarFiltros={cambiarFiltros}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      {spec.explorador.pestanias.length > 0 && (
        <section className={estilos.detalle} aria-label="Detalle">
          <div className={estilos.detalleCabecera}>
            <span className="kicker">Detalle</span>
            <h2>Las filas detrás de los números</h2>
          </div>
          <Explorador workspaceId={workspaceId} spec={spec} filtros={filtrosSerializados} />
        </section>
      )}
    </Marco>
  );
}
