/* Constructor: subir archivos, seguir la ingesta y ver las fuentes con su
   esquema. */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pedir, rutaWorkspace } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Marco } from "../compartido/componentes/Marco";
import { formatearCelda, formatearFecha, formatearNumero } from "../compartido/formato";
import { useSesion } from "../compartido/sesion";
import type { Fuente, Muestra, Tarea } from "../tipos";
import estilos from "./Fuentes.module.css";

const EXTENSIONES = ".csv,.txt,.tsv,.xlsx,.xlsm";

export function Fuentes() {
  const { usuario } = useSesion();
  const workspaceId = usuario?.workspace_id ?? 0;
  const clienteConsultas = useQueryClient();
  const entrada = useRef<HTMLInputElement>(null);
  const [tareas, setTareas] = useState<string[]>([]);

  const fuentes = useQuery({ queryKey: ["fuentes", workspaceId], queryFn: () => pedir<Fuente[]>(rutaWorkspace(workspaceId, "/fuentes")) });

  const subir = useMutation({
    mutationFn: async (archivos: FileList) => {
      const datos = new FormData();
      for (const archivo of Array.from(archivos)) datos.append("archivos", archivo);
      return pedir<Tarea[]>(rutaWorkspace(workspaceId, "/fuentes"), { method: "POST", body: datos });
    },
    onSuccess: (nuevas) => {
      setTareas((actuales) => [...nuevas.map((tarea) => tarea.id), ...actuales]);
      if (entrada.current) entrada.current.value = "";
    },
  });

  const borrar = useMutation({
    mutationFn: (fuente: Fuente) => pedir<void>(rutaWorkspace(workspaceId, `/fuentes/${fuente.id}`), { method: "DELETE" }),
    onSuccess: () => {
      void clienteConsultas.invalidateQueries({ queryKey: ["fuentes", workspaceId] });
    },
  });

  const alTerminar = () => {
    void clienteConsultas.invalidateQueries({ queryKey: ["fuentes", workspaceId] });
    void clienteConsultas.invalidateQueries({ queryKey: ["dashboard", workspaceId] });
  };

  return (
    <Marco kicker={`UBoard · ${usuario?.organizacion?.nombre ?? ""}`} titulo="Fuentes">
      <div className={estilos.pagina}>
        <section className={estilos.subida}>
          <div>
            <h2>Subí tus archivos</h2>
            <p className="secundario">
              CSV o Excel, de a uno o varios. UBoard detecta el separador, el encoding, los encabezados corridos y el tipo de cada columna. Un
              archivo con el mismo nombre reemplaza la fuente anterior.
            </p>
          </div>
          <div className={estilos.controlesSubida}>
            <input ref={entrada} className={estilos.archivo} type="file" multiple accept={EXTENSIONES} aria-label="Elegir archivos" />
            <button
              type="button"
              className="boton boton--primario"
              disabled={subir.isPending}
              onClick={() => {
                const archivos = entrada.current?.files;
                if (archivos && archivos.length) subir.mutate(archivos);
              }}
            >
              {subir.isPending ? "Subiendo…" : "Subir"}
            </button>
          </div>
          {subir.isError && <AvisoError error={subir.error} titulo="No se pudieron subir" />}
          {tareas.length > 0 && (
            <ul className={estilos.tareas}>
              {tareas.map((tareaId) => (
                <TareaEnCurso key={tareaId} workspaceId={workspaceId} tareaId={tareaId} alTerminar={alTerminar} />
              ))}
            </ul>
          )}
        </section>

        <section>
          <h2 className={estilos.subtitulo}>Fuentes cargadas</h2>
          {fuentes.isPending && <Cargando />}
          {fuentes.isError && <AvisoError error={fuentes.error} />}
          {fuentes.data && fuentes.data.length === 0 && <p className="mudo">Todavía no hay fuentes. Subí el primer archivo arriba.</p>}
          {fuentes.data && fuentes.data.length > 0 && (
            <div className={estilos.lista}>
              {fuentes.data.map((fuente) => (
                <TarjetaFuente key={fuente.id} workspaceId={workspaceId} fuente={fuente} onBorrar={() => borrar.mutate(fuente)} borrando={borrar.isPending} />
              ))}
            </div>
          )}
          {borrar.isError && <AvisoError error={borrar.error} titulo="No se pudo borrar" />}
        </section>
      </div>
    </Marco>
  );
}

function TareaEnCurso({ workspaceId, tareaId, alTerminar }: { workspaceId: number; tareaId: string; alTerminar: () => void }) {
  const tarea = useQuery({
    queryKey: ["tarea", workspaceId, tareaId],
    queryFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, `/tareas/${tareaId}`)),
    refetchInterval: (consulta) => {
      const estado = consulta.state.data?.estado;
      return estado === "pendiente" || estado === "corriendo" ? 800 : false;
    },
  });
  const estado = tarea.data?.estado;
  useEffect(() => {
    if (estado === "terminada" || estado === "error") alTerminar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [estado]);

  if (!tarea.data) return <li className="mudo">Encolando…</li>;
  const { progreso, mensaje, resultado, error } = tarea.data;
  return (
    <li className={estilos.tarea}>
      <div className={estilos.barraProgreso} aria-hidden="true">
        <span style={{ width: `${estado === "error" ? 100 : progreso}%` }} className={estado === "error" ? estilos.progresoError : undefined} />
      </div>
      <span>
        {estado === "terminada" && resultado?.fuentes
          ? resultado.fuentes.map((fuente) => `${fuente.nombre_tabla}: ${formatearNumero(fuente.filas, 0)} filas${fuente.reemplazada ? " (reemplazada)" : ""}`).join(" · ")
          : estado === "error"
            ? error
            : mensaje ?? "Procesando…"}
      </span>
    </li>
  );
}

function TarjetaFuente({ workspaceId, fuente, onBorrar, borrando }: { workspaceId: number; fuente: Fuente; onBorrar: () => void; borrando: boolean }) {
  const [verMuestra, setVerMuestra] = useState(false);
  const muestra = useQuery({
    queryKey: ["muestra", workspaceId, fuente.id, fuente.huella],
    queryFn: () => pedir<Muestra>(rutaWorkspace(workspaceId, `/fuentes/${fuente.id}/muestra?filas=8`)),
    enabled: verMuestra,
  });
  const confirmarBorrado = () => {
    if (window.confirm(`¿Borrar la fuente "${fuente.nombre_tabla}"? Si el modelo la usa, va a dejar de validar.`)) onBorrar();
  };

  return (
    <article className={estilos.tarjeta}>
      <header className={estilos.tarjetaCabecera}>
        <div>
          <h3 className={estilos.nombreTabla}>{fuente.nombre_tabla}</h3>
          <span className="mudo">
            {fuente.archivo_origen}
            {fuente.hoja ? ` · hoja ${fuente.hoja}` : ""} · {formatearNumero(fuente.filas, 0)} filas · actualizada {formatearFecha(fuente.actualizada_en)}
          </span>
        </div>
        <div className={estilos.acciones}>
          <button type="button" className="boton boton--chico" onClick={() => setVerMuestra((valor) => !valor)}>
            {verMuestra ? "Ocultar muestra" : "Ver muestra"}
          </button>
          <button type="button" className="boton boton--chico boton--peligro" onClick={confirmarBorrado} disabled={borrando}>
            Borrar
          </button>
        </div>
      </header>
      <ul className={estilos.columnas}>
        {fuente.columnas.map((columna) => (
          <li key={columna.nombre} className="pastilla" title={`${columna.nulos} nulos · ${columna.invalidos} inválidos${columna.nombre_origen && columna.nombre_origen !== columna.nombre ? ` · en el archivo: ${columna.nombre_origen}` : ""}`}>
            {columna.nombre} <span className={estilos.tipo}>{columna.tipo}</span>
            {columna.invalidos > 0 && <span className={estilos.invalidos}>{columna.invalidos} inválidos</span>}
          </li>
        ))}
      </ul>
      {verMuestra && muestra.isPending && <Cargando chico texto="Leyendo filas…" />}
      {verMuestra && muestra.isError && <AvisoError error={muestra.error} />}
      {verMuestra && muestra.data && (
        <div className={estilos.muestra}>
          <table className="tabla">
            <thead>
              <tr>
                {muestra.data.columnas.map((columna, indice) => (
                  <th key={columna} className={muestra.data.tipos[indice] === "entero" || muestra.data.tipos[indice] === "decimal" ? "numero" : undefined}>
                    {columna}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {muestra.data.filas.map((fila, indiceFila) => (
                <tr key={indiceFila}>
                  {fila.map((valor, indice) => (
                    <td key={indice} className={muestra.data.tipos[indice] === "entero" || muestra.data.tipos[indice] === "decimal" ? "numero" : undefined}>
                      {formatearCelda(valor, muestra.data.tipos[indice])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}
