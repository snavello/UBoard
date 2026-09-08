/* Los filtros del dashboard como chips: cada uno abre un popover con su
   control (lista con busqueda o rango de fechas con atajos). Los cambios se
   aplican al instante y viven en la URL. */
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { cantidadActivos } from "../compartido/filtrosUrl";
import { formatearFecha, hoyIso } from "../compartido/formato";
import type { FiltroSpec, FiltrosActivos, OpcionesSalida, SpecDashboard } from "../tipos";
import estilos from "./Filtros.module.css";

interface Props {
  workspaceId: number;
  spec: SpecDashboard;
  filtros: FiltrosActivos;
  onCambiar: (filtros: FiltrosActivos) => void;
}

type Rango = [string | null, string | null];

function valorLista(filtros: FiltrosActivos, id: string): string[] {
  const valor = filtros[id];
  return Array.isArray(valor) ? valor.map(String) : [];
}

function valorRango(filtros: FiltrosActivos, id: string): Rango {
  const valor = filtros[id];
  if (!Array.isArray(valor) || valor.length !== 2) return [null, null];
  return [valor[0] ? String(valor[0]) : null, valor[1] ? String(valor[1]) : null];
}

function resumenFiltro(filtro: FiltroSpec, filtros: FiltrosActivos): string | null {
  if (filtro.tipo === "lista") {
    const valores = valorLista(filtros, filtro.id);
    if (!valores.length) return null;
    return valores.length <= 2 ? valores.join(", ") : `${valores.length} seleccionados`;
  }
  const [desde, hasta] = valorRango(filtros, filtro.id);
  if (!desde && !hasta) return null;
  if (desde && hasta) return `${formatearFecha(desde)} – ${formatearFecha(hasta)}`;
  return desde ? `desde ${formatearFecha(desde)}` : `hasta ${formatearFecha(hasta)}`;
}

export function Filtros({ workspaceId, spec, filtros, onCambiar }: Props) {
  const [abierto, setAbierto] = useState<string | null>(null);
  const contenedor = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!abierto) return;
    const cerrarSiAfuera = (evento: MouseEvent) => {
      if (contenedor.current && !contenedor.current.contains(evento.target as Node)) setAbierto(null);
    };
    const cerrarConEscape = (evento: KeyboardEvent) => {
      if (evento.key === "Escape") setAbierto(null);
    };
    document.addEventListener("mousedown", cerrarSiAfuera);
    document.addEventListener("keydown", cerrarConEscape);
    return () => {
      document.removeEventListener("mousedown", cerrarSiAfuera);
      document.removeEventListener("keydown", cerrarConEscape);
    };
  }, [abierto]);

  if (!spec.filtros.length) return null;
  const activos = cantidadActivos(filtros);

  return (
    <div className={estilos.barra} ref={contenedor}>
      <span className={`${estilos.mostrando} mudo`}>{activos ? "Mostrando" : "Filtrar por"}</span>
      {spec.filtros.map((filtro) => {
        const resumen = resumenFiltro(filtro, filtros);
        const estaAbierto = abierto === filtro.id;
        return (
          <div key={filtro.id} className={estilos.chipEnvoltorio}>
            <button
              type="button"
              className={`${estilos.chip} ${resumen ? estilos.activo : ""}`}
              aria-expanded={estaAbierto}
              onClick={() => setAbierto(estaAbierto ? null : filtro.id)}
            >
              <span>{filtro.etiqueta ?? filtro.campo}</span>
              {resumen && <span className={estilos.resumen}>{resumen}</span>}
            </button>
            {estaAbierto && (
              <div className={estilos.popover} role="dialog" aria-label={filtro.etiqueta ?? filtro.campo}>
                {filtro.tipo === "lista" ? (
                  <ControlLista
                    workspaceId={workspaceId}
                    filtro={filtro}
                    seleccion={valorLista(filtros, filtro.id)}
                    onCambiar={(valores) => onCambiar({ ...filtros, [filtro.id]: valores })}
                  />
                ) : (
                  <ControlRango
                    workspaceId={workspaceId}
                    filtro={filtro}
                    rango={valorRango(filtros, filtro.id)}
                    onCambiar={(rango) => onCambiar({ ...filtros, [filtro.id]: rango })}
                  />
                )}
              </div>
            )}
          </div>
        );
      })}
      {activos > 0 && (
        <button type="button" className={`boton boton--texto boton--chico ${estilos.quitar}`} onClick={() => onCambiar({})}>
          Quitar filtros
        </button>
      )}
    </div>
  );
}

function useOpciones(workspaceId: number, filtro: FiltroSpec) {
  return useQuery({
    queryKey: ["opciones", workspaceId, filtro.id],
    queryFn: () => pedir<OpcionesSalida>(rutaWorkspace(workspaceId, `/dashboard/filtros/${filtro.id}/opciones`)),
    staleTime: 5 * 60_000,
  });
}

function ControlLista({
  workspaceId,
  filtro,
  seleccion,
  onCambiar,
}: {
  workspaceId: number;
  filtro: FiltroSpec;
  seleccion: string[];
  onCambiar: (valores: string[]) => void;
}) {
  const opciones = useOpciones(workspaceId, filtro);
  const [busqueda, setBusqueda] = useState("");
  const valores = (opciones.data?.valores ?? []).map(String);
  const visibles = valores.filter((valor) => valor.toLowerCase().includes(busqueda.toLowerCase()));

  const alternar = (valor: string) => {
    onCambiar(seleccion.includes(valor) ? seleccion.filter((otro) => otro !== valor) : [...seleccion, valor]);
  };

  return (
    <div className={estilos.lista}>
      {valores.length > 8 && (
        <input className="campo" type="search" placeholder="Buscar…" value={busqueda} onChange={(e) => setBusqueda(e.target.value)} autoFocus />
      )}
      <div className={estilos.opciones}>
        {opciones.isPending && <span className="mudo">Cargando opciones…</span>}
        {opciones.isError && <span className={estilos.error}>No pudimos cargar las opciones.</span>}
        {visibles.map((valor) => (
          <label key={valor} className={estilos.opcion}>
            <input type="checkbox" checked={seleccion.includes(valor)} onChange={() => alternar(valor)} />
            <span>{valor}</span>
          </label>
        ))}
        {opciones.isSuccess && !visibles.length && <span className="mudo">Nada coincide.</span>}
      </div>
      <div className={estilos.pieControl}>
        <span className="mudo">{seleccion.length ? `${seleccion.length} de ${valores.length}` : `${valores.length} valores`}</span>
        {seleccion.length > 0 && (
          <button type="button" className="boton boton--texto boton--chico" onClick={() => onCambiar([])}>
            Limpiar
          </button>
        )}
      </div>
    </div>
  );
}

function ControlRango({
  workspaceId,
  filtro,
  rango,
  onCambiar,
}: {
  workspaceId: number;
  filtro: FiltroSpec;
  rango: Rango;
  onCambiar: (rango: Rango) => void;
}) {
  const opciones = useOpciones(workspaceId, filtro);
  const [desde, hasta] = rango;
  const hoy = hoyIso();
  const anio = hoy.slice(0, 4);
  const mes = hoy.slice(0, 7);

  const atajos: { etiqueta: string; rango: Rango }[] = [
    { etiqueta: "Este mes", rango: [`${mes}-01`, hoy] },
    { etiqueta: "Este año", rango: [`${anio}-01-01`, hoy] },
    { etiqueta: "Últimos 90 días", rango: [restarDias(hoy, 90), hoy] },
    { etiqueta: "Todo", rango: [null, null] },
  ];

  return (
    <div className={estilos.rango}>
      <div className={estilos.fechas}>
        <label className="etiqueta">
          Desde
          <input
            className="campo"
            type="date"
            value={desde ?? ""}
            min={opciones.data?.minimo?.slice(0, 10)}
            max={hasta ?? opciones.data?.maximo?.slice(0, 10)}
            onChange={(e) => onCambiar([e.target.value || null, hasta])}
          />
        </label>
        <label className="etiqueta">
          Hasta
          <input
            className="campo"
            type="date"
            value={hasta ?? ""}
            min={desde ?? opciones.data?.minimo?.slice(0, 10)}
            max={opciones.data?.maximo?.slice(0, 10)}
            onChange={(e) => onCambiar([desde, e.target.value || null])}
          />
        </label>
      </div>
      <div className={estilos.atajos}>
        {atajos.map((atajo) => (
          <button key={atajo.etiqueta} type="button" className="boton boton--chico" onClick={() => onCambiar(atajo.rango)}>
            {atajo.etiqueta}
          </button>
        ))}
      </div>
      {opciones.data?.minimo && opciones.data.maximo && (
        <span className="mudo">
          Hay datos del {formatearFecha(opciones.data.minimo)} al {formatearFecha(opciones.data.maximo)}.
        </span>
      )}
    </div>
  );
}

function restarDias(iso: string, dias: number): string {
  const fecha = new Date(`${iso}T00:00:00`);
  fecha.setDate(fecha.getDate() - dias);
  return `${fecha.getFullYear()}-${String(fecha.getMonth() + 1).padStart(2, "0")}-${String(fecha.getDate()).padStart(2, "0")}`;
}
