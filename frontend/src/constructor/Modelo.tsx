/* Constructor: "Revision" es el wizard de la fase 2 (semaforos, operaciones
   granulares) para el modelo; "Avanzado" es el editor JSON de la fase 1,
   que sigue sirviendo para pegar un modelo entero o para el spec del
   dashboard (el wizard del spec llega en el paso 14). */
import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { codigoDeError, ErrorApi, pedir, rutaWorkspace } from "../compartido/api";
import { Aviso, AvisoError, ListaErrores } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Marco } from "../compartido/componentes/Marco";
import { Pestanias } from "../compartido/componentes/Pestanias";
import { resumirDiff } from "../compartido/diff";
import { formatearFecha } from "../compartido/formato";
import { useSesion } from "../compartido/sesion";
import { Revision } from "./Revision";
import type { ResultadoValidacion, VersionCompleta, VersionResumen } from "../tipos";
import estilos from "./Modelo.module.css";

type Pestania = "revision" | "modelo" | "dashboard";

const DESCRIPCION: Record<"modelo" | "dashboard", { titulo: string; ayuda: string; sinVersion: string; plantilla: string }> = {
  modelo: {
    titulo: "Modelo semántico",
    ayuda: "Entidades, campos, relaciones, métricas y dimensiones de tiempo. Cada campo apunta a una columna de una fuente cargada.",
    sinVersion: "E-MOD-02",
    plantilla: JSON.stringify(
      { version: 1, entidades: [{ id: "ventas", nombre: "Ventas", fuente: "ventas", tipo: "hechos", clave_primaria: ["id_venta"], campos: [{ id: "id_venta", columna_origen: "id_venta", nombre: "ID venta", tipo_dato: "entero", tipo_semantico: "identificador" }] }], relaciones: [], metricas: [], dimensiones_tiempo: [] },
      null,
      2,
    ),
  },
  dashboard: {
    titulo: "Dashboard",
    ayuda: "Filtros, KPIs, gráficos y pestañas del explorador, todo en términos del modelo. Se valida compilando cada panel.",
    sinVersion: "E-SPEC-02",
    plantilla: JSON.stringify({ version: 1, titulo: "Mi tablero", filtros: [], kpis: [], graficos: [], explorador: { pestanias: [] } }, null, 2),
  },
};

export function Modelo() {
  const { usuario } = useSesion();
  const [activa, setActiva] = useState<Pestania>("revision");
  const workspaceId = usuario?.workspace_id ?? 0;
  return (
    <Marco kicker={`UBoard · ${usuario?.organizacion?.nombre ?? ""}`} titulo="Modelo y dashboard">
      <Pestanias
        pestanias={[
          { id: "revision", titulo: "Revisión" },
          { id: "modelo", titulo: "Avanzado" },
          { id: "dashboard", titulo: "Dashboard" },
        ]}
        activa={activa}
        onCambiar={(id) => setActiva(id as Pestania)}
      />
      {activa === "revision" && <Revision workspaceId={workspaceId} />}
      {activa !== "revision" && <EditorJson key={activa} artefacto={activa} workspaceId={workspaceId} />}
    </Marco>
  );
}

function EditorJson({ artefacto, workspaceId }: { artefacto: "modelo" | "dashboard"; workspaceId: number }) {
  const descripcion = DESCRIPCION[artefacto];
  const clienteConsultas = useQueryClient();
  const ruta = rutaWorkspace(workspaceId, `/${artefacto}`);
  const [texto, setTexto] = useState("");
  const [tocado, setTocado] = useState(false);
  const [validacion, setValidacion] = useState<ResultadoValidacion | null>(null);
  const entradaArchivo = useRef<HTMLInputElement>(null);

  const actual = useQuery({
    queryKey: [artefacto, workspaceId],
    queryFn: () => pedir<VersionCompleta>(ruta),
    retry: false,
  });
  const versiones = useQuery({ queryKey: [artefacto, workspaceId, "versiones"], queryFn: () => pedir<VersionResumen[]>(`${ruta}/versiones`) });

  useEffect(() => {
    if (tocado) return;
    if (actual.data) setTexto(JSON.stringify(actual.data.contenido, null, 2));
    else if (actual.isError && codigoDeError(actual.error) === descripcion.sinVersion) setTexto(descripcion.plantilla);
  }, [actual.data, actual.isError, actual.error, tocado, descripcion]);

  const parsear = (): unknown => {
    try {
      return JSON.parse(texto);
    } catch (error) {
      throw new ErrorApi(400, { codigo: "JSON", mensaje: `El texto no es JSON válido: ${(error as Error).message}` });
    }
  };

  const validar = useMutation({
    mutationFn: () => pedir<ResultadoValidacion>(`${ruta}/validar`, { method: "POST", json: parsear() }),
    onSuccess: setValidacion,
  });
  const guardar = useMutation({
    mutationFn: () => pedir<VersionCompleta>(ruta, { method: "PUT", json: parsear() }),
    onSuccess: (version) => {
      setValidacion({ valido: true, errores: [], resumen: `Versión ${version.numero} guardada · ${version.resumen ?? ""}` });
      setTocado(false);
      void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId] });
      void clienteConsultas.invalidateQueries({ queryKey: ["dashboard", workspaceId] });
    },
  });

  const cargarVersion = async (numero: number) => {
    const version = await pedir<VersionCompleta>(`${ruta}/versiones/${numero}`);
    setTexto(JSON.stringify(version.contenido, null, 2));
    setTocado(true);
    setValidacion(null);
  };

  const restaurar = useMutation({
    mutationFn: (numero: number) => pedir<VersionCompleta>(`${ruta}/versiones/${numero}/restaurar`, { method: "POST" }),
    onSuccess: (version, numeroRestaurado) => {
      setTexto(JSON.stringify(version.contenido, null, 2));
      setTocado(false);
      setValidacion({ valido: true, errores: [], resumen: `Versión ${version.numero} guardada: se restauró la ${numeroRestaurado}.` });
      void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId] });
      void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId, "versiones"] });
      void clienteConsultas.invalidateQueries({ queryKey: ["dashboard", workspaceId] });
    },
  });

  const cargarArchivo = async (archivo: File | undefined) => {
    if (!archivo) return;
    setTexto(await archivo.text());
    setTocado(true);
    setValidacion(null);
    if (entradaArchivo.current) entradaArchivo.current.value = "";
  };

  const errorFatal = actual.isError && codigoDeError(actual.error) !== descripcion.sinVersion ? actual.error : null;

  return (
    <div className={estilos.editor}>
      <div className={estilos.columnaEditor}>
        <div>
          <h2>{descripcion.titulo}</h2>
          <p className="secundario">{descripcion.ayuda}</p>
        </div>
        {actual.isPending && <Cargando chico />}
        {errorFatal && <AvisoError error={errorFatal} />}
        {actual.data && !tocado && (
          <span className="mudo">
            Versión {actual.data.numero} · {actual.data.resumen} · {formatearFecha(actual.data.creada_en)}
          </span>
        )}
        {actual.isError && codigoDeError(actual.error) === descripcion.sinVersion && !tocado && (
          <Aviso tipo="info">Todavía no hay una versión guardada. Pegá el JSON o cargalo desde un archivo.</Aviso>
        )}
        <textarea
          className={`campo ${estilos.texto}`}
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value);
            setTocado(true);
            setValidacion(null);
          }}
          spellCheck={false}
          rows={28}
          aria-label={`JSON del ${descripcion.titulo}`}
        />
        <div className={estilos.acciones}>
          <button type="button" className="boton" onClick={() => validar.mutate()} disabled={validar.isPending || !texto.trim()}>
            {validar.isPending ? "Validando…" : "Validar"}
          </button>
          <button type="button" className="boton boton--primario" onClick={() => guardar.mutate()} disabled={guardar.isPending || !texto.trim()}>
            {guardar.isPending ? "Guardando…" : "Guardar versión"}
          </button>
          <label className="boton">
            Cargar archivo .json
            <input ref={entradaArchivo} type="file" accept=".json,application/json" className="visualmente-oculto" onChange={(e) => void cargarArchivo(e.target.files?.[0])} />
          </label>
        </div>
        {validar.isError && <AvisoError error={validar.error} titulo="No se pudo validar" />}
        {guardar.isError && (
          <Aviso tipo="error" titulo="No se guardó">
            {(guardar.error as ErrorApi).cuerpo?.mensaje ?? String(guardar.error)}
            {guardar.error instanceof ErrorApi && guardar.error.cuerpo.errores && <ListaErrores errores={guardar.error.cuerpo.errores} />}
          </Aviso>
        )}
        {validacion && (
          <Aviso tipo={validacion.valido ? "exito" : "error"} titulo={validacion.valido ? "Válido" : `${validacion.errores.length} error(es)`}>
            {validacion.resumen}
            <ListaErrores errores={validacion.errores} />
          </Aviso>
        )}
      </div>
      <aside className={estilos.columnaVersiones}>
        <h3>Versiones</h3>
        {versiones.data && versiones.data.length === 0 && <span className="mudo">Ninguna todavía.</span>}
        {restaurar.isError && <AvisoError error={restaurar.error} titulo="No se pudo restaurar" />}
        <ul className={estilos.versiones}>
          {versiones.data?.map((version, indice) => (
            <li key={version.numero} className={estilos.versionItem}>
              <button type="button" className={estilos.version} onClick={() => void cargarVersion(version.numero)}>
                <strong>v{version.numero}</strong>
                <span className="mudo">{formatearFecha(version.creada_en)}</span>
                <span className="secundario">{version.resumen}</span>
                {resumirDiff(version.diff).map((linea) => (
                  <span key={linea} className={estilos.diffLinea}>
                    {linea}
                  </span>
                ))}
              </button>
              {indice > 0 && (
                <button
                  type="button"
                  className="boton boton--chico boton--texto"
                  disabled={restaurar.isPending}
                  onClick={() => restaurar.mutate(version.numero)}
                  title={`Volver a esta versión (queda como versión ${(versiones.data?.[0]?.numero ?? version.numero) + 1} nueva)`}
                >
                  {restaurar.isPending && restaurar.variables === version.numero ? "Restaurando…" : "Restaurar esta versión"}
                </button>
              )}
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}
