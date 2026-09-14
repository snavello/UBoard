/* Constructor: subir archivos, seguir la ingesta y ver las fuentes con su
   esquema. */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";

import { pedir, rutaWorkspace } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Marco } from "../compartido/componentes/Marco";
import { resumirDiffEsquema } from "../compartido/diff";
import { formatearCelda, formatearFecha, formatearNumero } from "../compartido/formato";
import { useSesion } from "../compartido/sesion";
import type { Fuente, Muestra, PerfilFuente, ProblemaCalidad, RecetaTexto, ReporteCalidad, Tarea } from "../tipos";
import estilos from "./Fuentes.module.css";

const EXTENSIONES = ".csv,.txt,.tsv,.xlsx,.xlsm";

export function Fuentes() {
  const { usuario } = useSesion();
  const workspaceId = usuario?.workspace_id ?? 0;
  const clienteConsultas = useQueryClient();
  const entrada = useRef<HTMLInputElement>(null);
  const [tareas, setTareas] = useState<string[]>([]);
  const [terminadas, setTerminadas] = useState<string[]>([]);
  const [tareaPropuesta, setTareaPropuesta] = useState<string | null>(null);
  const ingestasCorriendo = tareas.some((tareaId) => !terminadas.includes(tareaId));

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

  const alTerminar = (tareaId: string) => {
    setTerminadas((actuales) => (actuales.includes(tareaId) ? actuales : [...actuales, tareaId]));
    void clienteConsultas.invalidateQueries({ queryKey: ["fuentes", workspaceId] });
    void clienteConsultas.invalidateQueries({ queryKey: ["dashboard", workspaceId] });
  };

  const proponer = useMutation({
    mutationFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, "/modelo/proponer"), { method: "POST" }),
    onSuccess: (tarea) => setTareaPropuesta(tarea.id),
  });
  const alTerminarPropuesta = () => {
    void clienteConsultas.invalidateQueries({ queryKey: ["modelo", workspaceId] });
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
                <TareaEnCurso key={tareaId} workspaceId={workspaceId} tareaId={tareaId} alTerminar={() => alTerminar(tareaId)} />
              ))}
            </ul>
          )}
        </section>

        <SeccionTextoEstructurado
          workspaceId={workspaceId}
          onIngestaEncolada={(tareaId) => setTareas((actuales) => [tareaId, ...actuales])}
        />

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

        {fuentes.data && fuentes.data.length > 0 && (
          <section className={estilos.proponer}>
            <div>
              <h2>Proponer el modelo</h2>
              <p className="secundario">
                {ingestasCorriendo
                  ? "Esperá a que terminen las ingestas: la propuesta se arma con todas las fuentes juntas."
                  : "Con las fuentes cargadas, UBoard busca claves, relaciones y tipos de cada columna y arma una propuesta de modelo. Lo que ya confirmaste o rechazaste en el modelo se respeta."}
              </p>
            </div>
            <div className={estilos.controlesSubida}>
              <button type="button" className="boton boton--primario" disabled={ingestasCorriendo || proponer.isPending} onClick={() => proponer.mutate()}>
                {proponer.isPending ? "Encolando…" : "Proponer modelo"}
              </button>
            </div>
            {proponer.isError && <AvisoError error={proponer.error} titulo="No se pudo proponer el modelo" />}
            {tareaPropuesta && (
              <ul className={estilos.tareas}>
                <PropuestaEnCurso key={tareaPropuesta} workspaceId={workspaceId} tareaId={tareaPropuesta} alTerminar={alTerminarPropuesta} />
              </ul>
            )}
          </section>
        )}
      </div>
    </Marco>
  );
}

/* Texto estructurado (fase 4): un boton separado y explicito (nunca un
   fallback automatico si el CSV falla, ".txt" ya es sinonimo de CSV
   delimitado hoy). Flujo de dos pasos: proponer (Claude arma una receta
   sobre una muestra) -> revisar/ajustar -> confirmar (recien ahi se
   ingesta el archivo entero, con la misma tarea ingesta.procesar_archivo
   de siempre). */
function SeccionTextoEstructurado({ workspaceId, onIngestaEncolada }: { workspaceId: number; onIngestaEncolada: (tareaId: string) => void }) {
  const entrada = useRef<HTMLInputElement>(null);
  const [tareaPropuesta, setTareaPropuesta] = useState<string | null>(null);

  const proponer = useMutation({
    mutationFn: async (archivo: File) => {
      const datos = new FormData();
      datos.append("archivo", archivo);
      return pedir<Tarea>(rutaWorkspace(workspaceId, "/fuentes/estructura/proponer"), { method: "POST", body: datos });
    },
    onSuccess: (tarea) => {
      setTareaPropuesta(tarea.id);
      if (entrada.current) entrada.current.value = "";
    },
  });

  return (
    <section className={estilos.estructura}>
      <div>
        <h2>Texto estructurado</h2>
        <p className="secundario">
          Para archivos de texto sin un separador estándar (por ejemplo, reportes de ancho fijo de sistemas viejos): Claude mira una muestra y
          propone cómo partirlo en columnas. Vas a poder revisar la propuesta antes de ingestar el archivo entero.
        </p>
      </div>
      <div className={estilos.controlesSubida}>
        <input ref={entrada} className={estilos.archivo} type="file" aria-label="Elegir archivo de texto" />
        <button
          type="button"
          className="boton boton--primario"
          disabled={proponer.isPending}
          onClick={() => {
            const archivo = entrada.current?.files?.[0];
            if (archivo) proponer.mutate(archivo);
          }}
        >
          {proponer.isPending ? "Analizando…" : "Interpretar con Claude"}
        </button>
      </div>
      {proponer.isError && <AvisoError error={proponer.error} titulo="No se pudo interpretar el archivo" />}
      {tareaPropuesta && (
        <PropuestaEstructura
          key={tareaPropuesta}
          workspaceId={workspaceId}
          tareaId={tareaPropuesta}
          onDescartar={() => setTareaPropuesta(null)}
          onConfirmada={(tareaIngestaId) => {
            setTareaPropuesta(null);
            onIngestaEncolada(tareaIngestaId);
          }}
        />
      )}
    </section>
  );
}

function PropuestaEstructura({
  workspaceId,
  tareaId,
  onDescartar,
  onConfirmada,
}: {
  workspaceId: number;
  tareaId: string;
  onDescartar: () => void;
  onConfirmada: (tareaIngestaId: string) => void;
}) {
  const tarea = useQuery({
    queryKey: ["tarea", workspaceId, tareaId],
    queryFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, `/tareas/${tareaId}`)),
    refetchIntervalInBackground: true,
    refetchInterval: (consulta) => {
      const estado = consulta.state.data?.estado;
      return estado === "pendiente" || estado === "corriendo" ? 800 : false;
    },
  });
  const [receta, setReceta] = useState<RecetaTexto | null>(null);
  useEffect(() => {
    if (tarea.data?.estado === "terminada" && tarea.data.resultado?.receta && !receta) {
      setReceta(tarea.data.resultado.receta);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tarea.data?.estado]);

  const confirmar = useMutation({
    mutationFn: (recetaFinal: RecetaTexto) =>
      pedir<Tarea>(rutaWorkspace(workspaceId, "/fuentes/estructura/confirmar"), {
        method: "POST",
        json: { tarea_id: tareaId, receta: recetaFinal },
      }),
    onSuccess: (tareaIngesta) => onConfirmada(tareaIngesta.id),
  });

  if (!tarea.data || tarea.data.estado === "pendiente" || tarea.data.estado === "corriendo") {
    return (
      <div className={estilos.tarea}>
        <div className={estilos.barraProgreso} aria-hidden="true">
          <span style={{ width: `${tarea.data?.progreso ?? 0}%` }} />
        </div>
        <span>{tarea.data?.mensaje ?? "Encolando…"}</span>
      </div>
    );
  }

  if (tarea.data.estado === "error") {
    return <AvisoError error={new Error(tarea.data.error ?? "Error desconocido")} titulo="No se pudo interpretar el archivo" />;
  }

  if (!receta) return null;
  const muestra = tarea.data.resultado?.muestra ?? [];

  return (
    <div className={estilos.recetaPreview}>
      <p className="secundario">
        {receta.modo === "ancho_fijo" ? "Detectamos columnas por posición (ancho fijo). " : `Detectamos un patrón repetido por línea. `}
        Revisá los nombres antes de confirmar (podés cambiarlos).
      </p>
      <ul className={estilos.columnasReceta}>
        {receta.columnas.map((columna, indice) => (
          <li key={indice} className={estilos.campoReceta}>
            <label className="etiqueta">
              {receta.modo === "ancho_fijo" ? `Posición ${columna.inicio}–${columna.fin}` : `Columna ${indice + 1} del patrón`}
              <input
                className="campo"
                value={columna.nombre}
                onChange={(evento) => {
                  const nombre = evento.target.value;
                  setReceta((actual) =>
                    actual ? { ...actual, columnas: actual.columnas.map((c, i) => (i === indice ? { ...c, nombre } : c)) } : actual,
                  );
                }}
              />
            </label>
          </li>
        ))}
      </ul>
      {muestra.length > 0 && (
        <details className={estilos.muestraTexto}>
          <summary>Ver la muestra que analizó Claude</summary>
          <pre>{muestra.join("\n")}</pre>
        </details>
      )}
      <div className={estilos.controlesSubida}>
        <button type="button" className="boton boton--primario" disabled={confirmar.isPending} onClick={() => confirmar.mutate(receta)}>
          {confirmar.isPending ? "Confirmando…" : "Confirmar e ingestar"}
        </button>
        <button type="button" className="boton boton--chico" onClick={onDescartar} disabled={confirmar.isPending}>
          Descartar
        </button>
      </div>
      {confirmar.isError && <AvisoError error={confirmar.error} titulo="No se pudo confirmar" />}
    </div>
  );
}

function TareaEnCurso({ workspaceId, tareaId, alTerminar }: { workspaceId: number; tareaId: string; alTerminar: () => void }) {
  const tarea = useQuery({
    queryKey: ["tarea", workspaceId, tareaId],
    queryFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, `/tareas/${tareaId}`)),
    refetchIntervalInBackground: true, // el polling sigue aunque la pestania no este visible
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
      {estado === "terminada" && resultado?.fuentes ? (
        resultado.fuentes.map((fuente) => {
          const diff = fuente.diff_esquema ? resumirDiffEsquema(fuente.diff_esquema) : null;
          return (
            <div key={fuente.id} className={estilos.resultadoFuente}>
              <span>
                {fuente.nombre_tabla}: {formatearNumero(fuente.filas, 0)} filas{fuente.reemplazada ? " (reemplazada)" : ""}
              </span>
              {/* Resubida con deteccion de cambios (fase 4): solo hay diff cuando se pisa una fuente que ya existia. */}
              {diff && (
                <span className={`mudo ${estilos.diffEsquema}`}>
                  {diff.resumen}
                  {diff.advertencia && <strong className={estilos.advertenciaDiff}> {diff.advertencia}</strong>}
                </span>
              )}
            </div>
          );
        })
      ) : (
        <span>{estado === "error" ? error : (mensaje ?? "Procesando…")}</span>
      )}
    </li>
  );
}

function PropuestaEnCurso({ workspaceId, tareaId, alTerminar }: { workspaceId: number; tareaId: string; alTerminar: () => void }) {
  const tarea = useQuery({
    queryKey: ["tarea", workspaceId, tareaId],
    queryFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, `/tareas/${tareaId}`)),
    refetchIntervalInBackground: true, // el polling sigue aunque la pestania no este visible
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
  const seguras = resultado?.relaciones?.filter((relacion) => relacion.confianza >= 0.9).length ?? 0;
  return (
    <li className={estilos.tarea}>
      <div className={estilos.barraProgreso} aria-hidden="true">
        <span style={{ width: `${estado === "error" ? 100 : progreso}%` }} className={estado === "error" ? estilos.progresoError : undefined} />
      </div>
      <span>
        {estado === "terminada" && resultado ? (
          <>
            Modelo propuesto (versión {resultado.version}): {resultado.resumen}
            {resultado.relaciones && resultado.relaciones.length > 0 ? `, ${seguras} con confianza alta` : ""}.{" "}
            {resultado.claude?.usado
              ? resultado.claude.cache
                ? "Nombres y métricas de Claude (respuesta guardada, sin costo). "
                : `Nombres y métricas de Claude (${formatearNumero((resultado.claude.tokens_entrada ?? 0) + (resultado.claude.tokens_salida ?? 0), 0)} tokens). `
              : resultado.claude?.advertencia
                ? `Solo heurísticas: ${resultado.claude.advertencia} `
                : ""}
            <Link to="/modelo">Revisalo en Modelo</Link>.
          </>
        ) : estado === "error" ? (
          error
        ) : (
          mensaje ?? "Analizando…"
        )}
      </span>
    </li>
  );
}

function TarjetaFuente({ workspaceId, fuente, onBorrar, borrando }: { workspaceId: number; fuente: Fuente; onBorrar: () => void; borrando: boolean }) {
  const [verMuestra, setVerMuestra] = useState(false);
  const [verPerfil, setVerPerfil] = useState(false);
  const [verCalidad, setVerCalidad] = useState(false);
  const perfil = useQuery({
    queryKey: ["perfil", workspaceId, fuente.id, fuente.huella, fuente.actualizada_en],
    queryFn: () => pedir<PerfilFuente>(rutaWorkspace(workspaceId, `/fuentes/${fuente.id}/perfil`)),
    enabled: verPerfil,
  });
  const muestra = useQuery({
    queryKey: ["muestra", workspaceId, fuente.id, fuente.huella],
    queryFn: () => pedir<Muestra>(rutaWorkspace(workspaceId, `/fuentes/${fuente.id}/muestra?filas=8`)),
    enabled: verMuestra,
  });
  const calidad = useQuery({
    queryKey: ["calidad", workspaceId, fuente.id, fuente.huella, fuente.actualizada_en],
    queryFn: () => pedir<ReporteCalidad>(rutaWorkspace(workspaceId, `/fuentes/${fuente.id}/calidad`)),
    enabled: verCalidad,
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
          <button type="button" className="boton boton--chico" onClick={() => setVerPerfil((valor) => !valor)} disabled={!fuente.perfilada} title={fuente.perfilada ? undefined : "Volvé a subir el archivo para calcular el perfil"}>
            {verPerfil ? "Ocultar perfil" : "Ver perfil"}
          </button>
          <button type="button" className="boton boton--chico" onClick={() => setVerMuestra((valor) => !valor)}>
            {verMuestra ? "Ocultar muestra" : "Ver muestra"}
          </button>
          <button type="button" className="boton boton--chico" onClick={() => setVerCalidad((valor) => !valor)}>
            {verCalidad ? "Ocultar calidad" : "Ver calidad"}
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
      {verPerfil && perfil.isPending && <Cargando chico texto="Leyendo el perfil…" />}
      {verPerfil && perfil.isError && <AvisoError error={perfil.error} />}
      {verPerfil && perfil.data && <TablaPerfil perfil={perfil.data} />}
      {verCalidad && calidad.isPending && <Cargando chico texto="Revisando la calidad…" />}
      {verCalidad && calidad.isError && <AvisoError error={calidad.error} />}
      {verCalidad && calidad.data && <ListaCalidad reporte={calidad.data} />}
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

const ICONO_SEVERIDAD: Record<ProblemaCalidad["severidad"], string> = { alta: "●", media: "◐", baja: "○" };
const ETIQUETA_SEVERIDAD: Record<ProblemaCalidad["severidad"], string> = { alta: "Alta", media: "Media", baja: "Baja" };

/* Reporte de calidad de datos (fase 4): traduce el perfil, el tipado y (si
   hay un modelo cargado) las claves y relaciones confirmadas en problemas
   priorizados. Nunca solo color: icono + palabra en cada nivel, mismo
   criterio que el Semaforo del wizard. */
function ListaCalidad({ reporte }: { reporte: ReporteCalidad }) {
  const claseSeveridad: Record<ProblemaCalidad["severidad"], string> = {
    alta: estilos.severidadAlta,
    media: estilos.severidadMedia,
    baja: estilos.severidadBaja,
  };
  if (reporte.problemas.length === 0) {
    return <p className={`secundario ${estilos.calidadVacia}`}>✓ No encontramos problemas de calidad en estos datos.</p>;
  }
  return (
    <ul className={estilos.calidad}>
      {reporte.problemas.map((problema, indice) => (
        <li key={indice} className={estilos.problemaCalidad}>
          <span className={`${estilos.severidad} ${claseSeveridad[problema.severidad]}`}>
            <span aria-hidden="true">{ICONO_SEVERIDAD[problema.severidad]}</span> {ETIQUETA_SEVERIDAD[problema.severidad]}
          </span>
          <span>{problema.mensaje}</span>
        </li>
      ))}
    </ul>
  );
}

const ETIQUETA_PATRON: Record<string, string> = { email: "emails", url: "URLs", numerico: "solo dígitos", codigo: "códigos" };

/* Estadisticas por columna calculadas en la ingesta. Es la evidencia que
   despues usan las heuristicas de claves y relaciones, mostrada tal cual. */
function TablaPerfil({ perfil }: { perfil: PerfilFuente }) {
  const candidatas = new Set(perfil.candidatas_clave);
  return (
    <div className={estilos.perfil}>
      <p className="secundario">
        {formatearNumero(perfil.filas, 0)} filas.{" "}
        {candidatas.size > 0 ? `Candidatas a clave: ${perfil.candidatas_clave.join(", ")}.` : "Ninguna columna sirve como clave: todas repiten valores o tienen nulos."}
      </p>
      <table className="tabla">
        <thead>
          <tr>
            <th>Columna</th>
            <th>Tipo</th>
            <th className="numero">Nulos</th>
            <th className="numero">Distintos</th>
            <th>Mín · máx</th>
            <th>Valores frecuentes</th>
          </tr>
        </thead>
        <tbody>
          {perfil.columnas.map((columna) => (
            <tr key={columna.nombre}>
              <td>
                <span className={estilos.nombreColumna}>{columna.nombre}</span>
                {candidatas.has(columna.nombre) && <span className="pastilla pastilla--acento">clave candidata</span>}
              </td>
              <td>
                {columna.tipo}
                {columna.patron && <span className="mudo"> · {ETIQUETA_PATRON[columna.patron] ?? columna.patron}</span>}
              </td>
              <td className={`numero${columna.nulos > 0 ? ` ${estilos.conNulos}` : ""}`}>{formatearNumero(columna.nulos, 0)}</td>
              <td className="numero">{formatearNumero(columna.distintos, 0)}</td>
              <td className={estilos.rango}>{rangoDe(columna.tipo, columna.minimo, columna.maximo, columna.longitud_minima, columna.longitud_maxima)}</td>
              <td className={estilos.frecuentes}>
                {columna.top_valores.slice(0, 5).map((top) => (
                  <span key={String(top.valor)} className="pastilla" title={`${formatearNumero(top.cantidad, 0)} filas`}>
                    {formatearCelda(top.valor, columna.tipo)} <span className="mudo">×{formatearNumero(top.cantidad, 0)}</span>
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function rangoDe(tipo: string, minimo: unknown, maximo: unknown, largoMin: number | null, largoMax: number | null): string {
  if (tipo === "texto") return largoMin == null || largoMax == null ? "—" : `${largoMin} a ${largoMax} caracteres`;
  if (minimo == null || maximo == null) return "—";
  return `${formatearCelda(minimo, tipo)} · ${formatearCelda(maximo, tipo)}`;
}
