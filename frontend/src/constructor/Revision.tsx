/* Wizard de revision del modelo semantico (fase 2, paso 13): entidades y
   campos, relaciones y metricas con semaforo de confianza. Cada accion es
   una operacion granular (POST /modelo/operaciones) que crea una version
   nueva; nunca se edita el JSON a mano aca (eso sigue en "Avanzado"). */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AvisoError, Aviso, ListaErrores } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Semaforo } from "../compartido/componentes/Semaforo";
import { codigoDeError, ErrorApi, pedir, rutaWorkspace } from "../compartido/api";
import { formatearFecha, formatearNumero } from "../compartido/formato";
import type {
  Agregacion,
  Campo,
  EntidadModelo,
  ExpresionMetrica,
  Formato,
  Granularidad,
  MetricaModelo,
  ModeloSemantico,
  Operando,
  OperacionFormula,
  RelacionModelo,
  Tarea,
  TipoEntidad,
  TipoSemantico,
  VersionCompleta,
} from "../tipos";
import { esExpresionAgregacion, esExpresionCociente } from "../tipos";
import estilos from "./Revision.module.css";

const GRANULARIDADES: Granularidad[] = ["dia", "semana", "mes", "trimestre", "anio"];
const AGREGACIONES: Agregacion[] = ["suma", "conteo", "conteo_distinto", "promedio", "minimo", "maximo"];
const FORMATOS: Formato[] = ["moneda", "entero", "decimal", "porcentaje"];
const TIPOS_SEMANTICOS: TipoSemantico[] = [
  "identificador",
  "clave_foranea",
  "fecha",
  "monto",
  "cantidad",
  "porcentaje",
  "categoria",
  "texto_libre",
  "booleano",
  "geo",
];

const MOTIVO: Record<string, string> = {
  unica_candidata: "única columna posible",
  varias_candidatas_una_con_nombre_de_clave: "elegida por su nombre entre varias posibles",
  varias_candidatas: "elegida entre varias columnas posibles",
  sin_candidata: "ninguna columna calza del todo; revisala",
  relacion_propuesta: "clave foránea de una relación propuesta",
  tipo_de_dato: "por el tipo de dato",
  nombre: "por el nombre de la columna",
  rango_0_1: "los valores van de 0 a 1",
  decimal_sin_nombre_conocido: "es un decimal, sin más pistas",
  entero_con_pocos_valores: "entero con pocos valores distintos",
  entero_sin_nombre_conocido: "es un entero, sin más pistas",
  patron_email: "los valores parecen emails",
  patron_url: "los valores parecen URLs",
  patron_codigo: "los valores parecen códigos",
  patron_numerico: "los valores son numéricos",
  pocos_valores_distintos: "pocos valores distintos",
  texto_unico: "todos los valores son distintos",
  muchos_valores_distintos: "muchos valores distintos",
};

function describirEvidenciaCampo(campo: Campo): string | null {
  const motivo = campo.evidencia?.motivo;
  if (typeof motivo !== "string") return null;
  return MOTIVO[motivo] ?? motivo.replaceAll("_", " ");
}

function describirEvidenciaRelacion(relacion: RelacionModelo): string {
  if (relacion.evidencia?.origen === "usuario") return "Creada a mano";
  const inclusion = relacion.evidencia?.inclusion;
  const huerfanos = relacion.evidencia?.huerfanos;
  const similar = relacion.evidencia?.nombre_similar;
  if (typeof inclusion !== "number") return "—";
  const partes = [`${formatearNumero(inclusion * 100, 0)} % de las filas coinciden`];
  if (typeof huerfanos === "number" && huerfanos > 0) partes.push(`${formatearNumero(huerfanos, 0)} huérfanas`);
  if (similar === false) partes.push("nombre distinto");
  return partes.join(", ");
}

const SIMBOLO_OPERACION_FORMULA: Record<OperacionFormula, string> = { suma: "+", resta: "−", multiplicacion: "×", division: "÷" };

function resumenOperando(operando: Operando): string {
  if (typeof operando === "number") return formatearNumero(operando, 2);
  if (typeof operando === "string") return operando;
  return `(${resumenOperando(operando.izquierda)} ${SIMBOLO_OPERACION_FORMULA[operando.operacion]} ${resumenOperando(operando.derecha)})`;
}

function resumenExpresion(metrica: MetricaModelo): string {
  if (esExpresionAgregacion(metrica.expresion)) return `${metrica.expresion.agregacion}(${metrica.expresion.campo})`;
  if (esExpresionCociente(metrica.expresion)) return `${metrica.expresion.numerador} / ${metrica.expresion.denominador}`;
  return `${resumenOperando(metrica.expresion.izquierda)} ${SIMBOLO_OPERACION_FORMULA[metrica.expresion.operacion]} ${resumenOperando(metrica.expresion.derecha)}`;
}

function todosLosCampos(modelo: ModeloSemantico): { referencia: string; etiqueta: string; tipoDato: string }[] {
  return modelo.entidades.flatMap((entidad) =>
    entidad.campos.map((campo) => ({
      referencia: `${entidad.id}.${campo.id}`,
      etiqueta: `${entidad.nombre} · ${campo.nombre}`,
      tipoDato: campo.tipo_dato,
    })),
  );
}

export function Revision({ workspaceId }: { workspaceId: number }) {
  const clienteConsultas = useQueryClient();
  const actual = useQuery({ queryKey: ["modelo", workspaceId], queryFn: () => pedir<VersionCompleta>(rutaWorkspace(workspaceId, "/modelo")), retry: false });
  const [tareaSpec, setTareaSpec] = useState<string | null>(null);

  const aplicar = useMutation({
    mutationFn: (operacion: Record<string, unknown>) => pedir<VersionCompleta>(rutaWorkspace(workspaceId, "/modelo/operaciones"), { method: "POST", json: operacion }),
    onSuccess: () => {
      void clienteConsultas.invalidateQueries({ queryKey: ["modelo", workspaceId] });
      void clienteConsultas.invalidateQueries({ queryKey: ["dashboard", workspaceId] });
    },
  });
  const proponerSpec = useMutation({
    mutationFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, "/dashboard/proponer"), { method: "POST" }),
    onSuccess: (tarea) => setTareaSpec(tarea.id),
  });

  if (actual.isPending) return <Cargando />;
  if (actual.isError && codigoDeError(actual.error) === "E-MOD-02") {
    return (
      <Aviso tipo="info" titulo="Todavía no hay un modelo">
        Subí tus archivos en <Link to="/fuentes">Fuentes</Link> y usá "Proponer modelo", o pegá un JSON a mano en la
        pestaña Avanzado.
      </Aviso>
    );
  }
  if (actual.isError) return <AvisoError error={actual.error} />;

  const modelo = actual.data!.contenido as unknown as ModeloSemantico;
  const version = actual.data!;

  return (
    <div className={estilos.revision}>
      <header className={estilos.cabecera}>
        <div>
          <span className="mudo">
            Versión {version.numero} · {formatearFecha(version.creada_en)}
          </span>
          <p className="secundario">{version.resumen}</p>
        </div>
        <button type="button" className="boton boton--primario" disabled={aplicar.isPending} onClick={() => aplicar.mutate({ operacion: "confirmar_todo", seccion: "todo" })}>
          Confirmar todo lo verde
        </button>
      </header>
      {aplicar.isError && (
        <Aviso tipo="error" titulo="No se pudo aplicar">
          {(aplicar.error as ErrorApi).cuerpo?.mensaje ?? String(aplicar.error)}
          {aplicar.error instanceof ErrorApi && aplicar.error.cuerpo.errores && <ListaErrores errores={aplicar.error.cuerpo.errores} />}
        </Aviso>
      )}

      <SeccionEntidades modelo={modelo} aplicar={aplicar.mutateAsync} pendiente={aplicar.isPending} />
      <SeccionRelaciones modelo={modelo} aplicar={aplicar.mutateAsync} pendiente={aplicar.isPending} />
      <SeccionMetricas modelo={modelo} aplicar={aplicar.mutateAsync} pendiente={aplicar.isPending} />
      <SeccionDimensionesTiempo modelo={modelo} aplicar={aplicar.mutateAsync} pendiente={aplicar.isPending} />

      <section className={`${estilos.seccion} ${estilos.proponerDashboard}`}>
        <div>
          <h2>Proponer el dashboard</h2>
          <p className="secundario">
            Cuando estés conforme con el modelo, UBoard arma los filtros, KPIs, gráficos y el explorador a partir de
            lo confirmado, y Claude elige qué mostrar primero y cómo titular todo.
          </p>
        </div>
        <button type="button" className="boton boton--primario" disabled={proponerSpec.isPending} onClick={() => proponerSpec.mutate()}>
          {proponerSpec.isPending ? "Encolando…" : "Proponer dashboard"}
        </button>
        {proponerSpec.isError && <AvisoError error={proponerSpec.error} titulo="No se pudo proponer el dashboard" />}
        {tareaSpec && (
          <ul className={estilos.tareas}>
            <PropuestaSpecEnCurso
              key={tareaSpec}
              workspaceId={workspaceId}
              tareaId={tareaSpec}
              alTerminar={() => clienteConsultas.invalidateQueries({ queryKey: ["dashboard", workspaceId] })}
            />
          </ul>
        )}
      </section>
    </div>
  );
}

function PropuestaSpecEnCurso({ workspaceId, tareaId, alTerminar }: { workspaceId: number; tareaId: string; alTerminar: () => void }) {
  const tarea = useQuery({
    queryKey: ["tarea", workspaceId, tareaId],
    queryFn: () => pedir<Tarea>(rutaWorkspace(workspaceId, `/tareas/${tareaId}`)),
    refetchIntervalInBackground: true,
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
    <li className={estilos.tareaSpec}>
      <div className={estilos.barraProgreso} aria-hidden="true">
        <span style={{ width: `${estado === "error" ? 100 : progreso}%` }} className={estado === "error" ? estilos.progresoError : undefined} />
      </div>
      <span>
        {estado === "terminada" && resultado ? (
          <>
            Dashboard propuesto (versión {resultado.version}) "{resultado.titulo}": {resultado.resumen}.{" "}
            {resultado.claude?.usado
              ? resultado.claude.cache
                ? "Curado por Claude (respuesta guardada, sin costo). "
                : `Curado por Claude (${formatearNumero((resultado.claude.tokens_entrada ?? 0) + (resultado.claude.tokens_salida ?? 0), 0)} tokens). `
              : resultado.claude?.advertencia
                ? `Sin curar: ${resultado.claude.advertencia} `
                : ""}
            <Link to="/tablero">Mirá el tablero</Link>.
          </>
        ) : estado === "error" ? (
          error
        ) : (
          mensaje ?? "Armando…"
        )}
      </span>
    </li>
  );
}

type Aplicar = (operacion: Record<string, unknown>) => Promise<unknown>;

/* Texto que se vuelve un input al hacer click; guarda al perder el foco o
   con Enter, solo si cambió. */
function TextoEditable({ valor, onGuardar, className }: { valor: string; onGuardar: (nuevo: string) => void; className?: string }) {
  const [editando, setEditando] = useState(false);
  const [texto, setTexto] = useState(valor);
  if (!editando) {
    return (
      <button type="button" className={`${estilos.textoEditable} ${className ?? ""}`} onClick={() => { setTexto(valor); setEditando(true); }} title="Click para renombrar">
        {valor}
      </button>
    );
  }
  const confirmar = () => {
    setEditando(false);
    if (texto.trim() && texto !== valor) onGuardar(texto.trim());
  };
  return (
    <input
      className="campo"
      value={texto}
      autoFocus
      onChange={(e) => setTexto(e.target.value)}
      onBlur={confirmar}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") setEditando(false);
      }}
    />
  );
}

function SeccionEntidades({ modelo, aplicar, pendiente }: { modelo: ModeloSemantico; aplicar: Aplicar; pendiente: boolean }) {
  return (
    <section className={estilos.seccion}>
      <h2>Entidades y campos</h2>
      <div className={estilos.tarjetas}>
        {modelo.entidades.map((entidad) => (
          <EntidadTarjeta key={entidad.id} entidad={entidad} aplicar={aplicar} pendiente={pendiente} />
        ))}
      </div>
    </section>
  );
}

function EntidadTarjeta({ entidad, aplicar, pendiente }: { entidad: EntidadModelo; aplicar: Aplicar; pendiente: boolean }) {
  const [nuevoSinonimo, setNuevoSinonimo] = useState("");
  const pendientesEnEntidad = entidad.campos.some((campo) => campo.estado === "propuesta");

  return (
    <article className={estilos.tarjeta}>
      <header className={estilos.tarjetaCabecera}>
        <div className={estilos.tituloEntidad}>
          <TextoEditable valor={entidad.nombre} onGuardar={(nombre) => aplicar({ operacion: "renombrar_entidad", entidad: entidad.id, nombre })} className={estilos.nombreEntidad} />
          <span className="mudo codigo">{entidad.fuente}</span>
        </div>
        <div className={estilos.controlesEntidad}>
          <select
            className="campo"
            value={entidad.tipo}
            disabled={pendiente}
            onChange={(e) => aplicar({ operacion: "asignar_tipo_entidad", entidad: entidad.id, tipo: e.target.value as TipoEntidad })}
          >
            <option value="hechos">Hechos</option>
            <option value="dimension">Dimensión</option>
          </select>
          {pendientesEnEntidad && (
            <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "confirmar_todo", seccion: "campos", entidad: entidad.id })}>
              Confirmar lo verde
            </button>
          )}
        </div>
      </header>
      <div className={estilos.sinonimos}>
        {entidad.sinonimos.map((sinonimo) => (
          <span key={sinonimo} className="pastilla">
            {sinonimo}
            <button type="button" className={estilos.quitar} aria-label={`Quitar sinónimo ${sinonimo}`} disabled={pendiente} onClick={() => aplicar({ operacion: "quitar_sinonimo", entidad: entidad.id, sinonimo })}>
              ×
            </button>
          </span>
        ))}
        <form
          className={estilos.formInline}
          onSubmit={(e) => {
            e.preventDefault();
            if (nuevoSinonimo.trim()) {
              void aplicar({ operacion: "agregar_sinonimo", entidad: entidad.id, sinonimo: nuevoSinonimo.trim() });
              setNuevoSinonimo("");
            }
          }}
        >
          <input className="campo" placeholder="+ sinónimo" value={nuevoSinonimo} onChange={(e) => setNuevoSinonimo(e.target.value)} />
        </form>
      </div>
      <div className={estilos.tablaScroll}>
        <table className="tabla">
          <thead>
            <tr>
              <th>Campo</th>
              <th>Tipo semántico</th>
              <th>Motivo</th>
              <th>Estado</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {entidad.campos.map((campo) => {
              const esClave = entidad.clave_primaria.includes(campo.id);
              return (
                <tr key={campo.id}>
                  <td>
                    <TextoEditable valor={campo.nombre} onGuardar={(nombre) => aplicar({ operacion: "renombrar_campo", entidad: entidad.id, campo: campo.id, nombre })} />
                    {esClave && <span className="pastilla pastilla--acento">clave primaria</span>}
                  </td>
                  <td>
                    <select
                      className="campo"
                      value={campo.tipo_semantico}
                      disabled={pendiente || esClave}
                      onChange={(e) => aplicar({ operacion: "asignar_tipo_semantico", entidad: entidad.id, campo: campo.id, tipo_semantico: e.target.value as TipoSemantico })}
                    >
                      {TIPOS_SEMANTICOS.map((tipo) => (
                        <option key={tipo} value={tipo}>
                          {tipo}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="mudo">{describirEvidenciaCampo(campo) ?? "—"}</td>
                  <td>
                    <Semaforo estado={campo.estado} confianza={campo.confianza} />
                  </td>
                  <td className={estilos.acciones}>
                    {campo.estado !== "confirmada" && (
                      <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "confirmar_campo", entidad: entidad.id, campo: campo.id })}>
                        Confirmar
                      </button>
                    )}
                    {campo.estado !== "rechazada" && !esClave && (
                      <button type="button" className="boton boton--chico boton--peligro" disabled={pendiente} onClick={() => aplicar({ operacion: "rechazar_campo", entidad: entidad.id, campo: campo.id })}>
                        Rechazar
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function SeccionRelaciones({ modelo, aplicar, pendiente }: { modelo: ModeloSemantico; aplicar: Aplicar; pendiente: boolean }) {
  const campos = todosLosCampos(modelo);
  const [desde, setDesde] = useState("");
  const [hacia, setHacia] = useState("");
  const hayPropuestas = modelo.relaciones.some((relacion) => relacion.estado === "propuesta");

  return (
    <section className={estilos.seccion}>
      <div className={estilos.tituloSeccion}>
        <h2>Relaciones</h2>
        {hayPropuestas && (
          <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "confirmar_todo", seccion: "relaciones" })}>
            Confirmar lo verde
          </button>
        )}
      </div>
      {modelo.relaciones.length === 0 && <p className="mudo">Todavía no hay relaciones.</p>}
      <div className={estilos.tablaScroll}>
        <table className="tabla">
          <thead>
            <tr>
              <th>Desde</th>
              <th>Hacia</th>
              <th>Evidencia</th>
              <th>Confianza</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {modelo.relaciones.map((relacion) => (
              <tr key={relacion.id}>
                <td className="codigo">{relacion.desde.entidad}.{relacion.desde.campo}</td>
                <td className="codigo">{relacion.hacia.entidad}.{relacion.hacia.campo}</td>
                <td className="mudo">{describirEvidenciaRelacion(relacion)}</td>
                <td>
                  <Semaforo estado={relacion.estado} confianza={relacion.confianza} />
                </td>
                <td className={estilos.acciones}>
                  {relacion.estado !== "confirmada" && (
                    <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "confirmar_relacion", relacion: relacion.id })}>
                      Confirmar
                    </button>
                  )}
                  {relacion.estado !== "rechazada" && (
                    <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "rechazar_relacion", relacion: relacion.id })}>
                      Rechazar
                    </button>
                  )}
                  <button
                    type="button"
                    className="boton boton--chico boton--peligro"
                    disabled={pendiente}
                    onClick={() => {
                      if (window.confirm(`¿Eliminar la relación '${relacion.id}'?`)) void aplicar({ operacion: "eliminar_relacion", relacion: relacion.id });
                    }}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className={estilos.crear}>
        <summary>Crear una relación</summary>
        <form
          className={estilos.formCrear}
          onSubmit={(e) => {
            e.preventDefault();
            if (!desde || !hacia) return;
            const [entidadDesde, campoDesde] = desde.split(".");
            const [entidadHacia, campoHacia] = hacia.split(".");
            void aplicar({ operacion: "crear_relacion", desde: { entidad: entidadDesde, campo: campoDesde }, hacia: { entidad: entidadHacia, campo: campoHacia } });
          }}
        >
          <select className="campo" value={desde} onChange={(e) => setDesde(e.target.value)} required>
            <option value="">Desde…</option>
            {campos.map((campo) => (
              <option key={campo.referencia} value={campo.referencia}>
                {campo.etiqueta}
              </option>
            ))}
          </select>
          <span className="mudo">→</span>
          <select className="campo" value={hacia} onChange={(e) => setHacia(e.target.value)} required>
            <option value="">Hacia (clave primaria)…</option>
            {campos.map((campo) => (
              <option key={campo.referencia} value={campo.referencia}>
                {campo.etiqueta}
              </option>
            ))}
          </select>
          <button type="submit" className="boton boton--primario boton--chico" disabled={pendiente}>
            Crear
          </button>
        </form>
      </details>
    </section>
  );
}

function SeccionMetricas({ modelo, aplicar, pendiente }: { modelo: ModeloSemantico; aplicar: Aplicar; pendiente: boolean }) {
  const campos = todosLosCampos(modelo).filter((campo) => campo.tipoDato === "entero" || campo.tipoDato === "decimal");
  const hayPropuestas = modelo.metricas.some((metrica) => metrica.estado === "propuesta");
  const [id, setId] = useState("");
  const [nombre, setNombre] = useState("");
  const [tipo, setTipo] = useState<"agregacion" | "cociente" | "formula">("agregacion");
  const [agregacion, setAgregacion] = useState<Agregacion>("suma");
  const [campo, setCampo] = useState("");
  const [numerador, setNumerador] = useState("");
  const [denominador, setDenominador] = useState("");
  const [operacionFormula, setOperacionFormula] = useState<OperacionFormula>("resta");
  const [izqTipo, setIzqTipo] = useState<"metrica" | "numero">("metrica");
  const [izqMetrica, setIzqMetrica] = useState("");
  const [izqNumero, setIzqNumero] = useState("");
  const [derTipo, setDerTipo] = useState<"metrica" | "numero">("metrica");
  const [derMetrica, setDerMetrica] = useState("");
  const [derNumero, setDerNumero] = useState("");
  const [formato, setFormato] = useState<Formato>("decimal");

  const crear = (e: React.FormEvent) => {
    e.preventDefault();
    if (!id.trim() || !nombre.trim()) return;
    let expresion: ExpresionMetrica;
    if (tipo === "agregacion") {
      expresion = { agregacion, campo };
    } else if (tipo === "cociente") {
      expresion = { numerador, denominador };
    } else {
      const izquierda: Operando = izqTipo === "metrica" ? izqMetrica : Number(izqNumero);
      const derecha: Operando = derTipo === "metrica" ? derMetrica : Number(derNumero);
      expresion = { operacion: operacionFormula, izquierda, derecha };
    }
    void aplicar({ operacion: "crear_metrica", id: id.trim(), nombre: nombre.trim(), expresion, formato }).then(() => {
      setId("");
      setNombre("");
    });
  };

  return (
    <section className={estilos.seccion}>
      <div className={estilos.tituloSeccion}>
        <h2>Métricas</h2>
        {hayPropuestas && (
          <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "confirmar_todo", seccion: "metricas" })}>
            Confirmar lo verde
          </button>
        )}
      </div>
      {modelo.metricas.length === 0 && <p className="mudo">Todavía no hay métricas.</p>}
      <div className={estilos.tablaScroll}>
        <table className="tabla">
          <thead>
            <tr>
              <th>Métrica</th>
              <th>Expresión</th>
              <th>Formato</th>
              <th>Confianza</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {modelo.metricas.map((metrica) => (
              <tr key={metrica.id}>
                <td>
                  <TextoEditable valor={metrica.nombre} onGuardar={(nuevoNombre) => aplicar({ operacion: "editar_metrica", metrica: metrica.id, nombre: nuevoNombre })} />
                </td>
                <td className="codigo">{resumenExpresion(metrica)}</td>
                <td>{metrica.formato}</td>
                <td>
                  <Semaforo estado={metrica.estado} confianza={metrica.confianza} />
                </td>
                <td className={estilos.acciones}>
                  {metrica.estado !== "confirmada" && (
                    <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "confirmar_metrica", metrica: metrica.id })}>
                      Confirmar
                    </button>
                  )}
                  {metrica.estado !== "rechazada" && (
                    <button type="button" className="boton boton--chico" disabled={pendiente} onClick={() => aplicar({ operacion: "rechazar_metrica", metrica: metrica.id })}>
                      Rechazar
                    </button>
                  )}
                  <button
                    type="button"
                    className="boton boton--chico boton--peligro"
                    disabled={pendiente}
                    onClick={() => {
                      if (window.confirm(`¿Eliminar la métrica '${metrica.id}'?`)) void aplicar({ operacion: "eliminar_metrica", metrica: metrica.id });
                    }}
                  >
                    Eliminar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details className={estilos.crear}>
        <summary>Crear una métrica</summary>
        <form className={estilos.formCrear} onSubmit={crear}>
          <input className="campo" placeholder="id (ej. total_descuentos)" value={id} onChange={(e) => setId(e.target.value)} required />
          <input className="campo" placeholder="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} required />
          <select className="campo" value={tipo} onChange={(e) => setTipo(e.target.value as "agregacion" | "cociente" | "formula")}>
            <option value="agregacion">Agregación</option>
            <option value="cociente">Cociente</option>
            <option value="formula">Fórmula (+ − × ÷)</option>
          </select>
          {tipo === "agregacion" ? (
            <>
              <select className="campo" value={agregacion} onChange={(e) => setAgregacion(e.target.value as Agregacion)}>
                {AGREGACIONES.map((op) => (
                  <option key={op} value={op}>
                    {op}
                  </option>
                ))}
              </select>
              <select className="campo" value={campo} onChange={(e) => setCampo(e.target.value)} required>
                <option value="">Campo…</option>
                {campos.map((c) => (
                  <option key={c.referencia} value={c.referencia}>
                    {c.etiqueta}
                  </option>
                ))}
              </select>
            </>
          ) : tipo === "cociente" ? (
            <>
              <select className="campo" value={numerador} onChange={(e) => setNumerador(e.target.value)} required>
                <option value="">Numerador…</option>
                {modelo.metricas.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nombre}
                  </option>
                ))}
              </select>
              <select className="campo" value={denominador} onChange={(e) => setDenominador(e.target.value)} required>
                <option value="">Denominador…</option>
                {modelo.metricas.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.nombre}
                  </option>
                ))}
              </select>
            </>
          ) : (
            <>
              <CampoOperando
                etiqueta="Operando izquierdo"
                tipo={izqTipo}
                onTipo={setIzqTipo}
                metricaId={izqMetrica}
                onMetricaId={setIzqMetrica}
                numero={izqNumero}
                onNumero={setIzqNumero}
                metricas={modelo.metricas}
              />
              <select className="campo" value={operacionFormula} onChange={(e) => setOperacionFormula(e.target.value as OperacionFormula)}>
                <option value="suma">+ suma</option>
                <option value="resta">− resta</option>
                <option value="multiplicacion">× multiplicación</option>
                <option value="division">÷ división</option>
              </select>
              <CampoOperando
                etiqueta="Operando derecho"
                tipo={derTipo}
                onTipo={setDerTipo}
                metricaId={derMetrica}
                onMetricaId={setDerMetrica}
                numero={derNumero}
                onNumero={setDerNumero}
                metricas={modelo.metricas}
              />
            </>
          )}
          <select className="campo" value={formato} onChange={(e) => setFormato(e.target.value as Formato)}>
            {FORMATOS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <button type="submit" className="boton boton--primario boton--chico" disabled={pendiente}>
            Crear
          </button>
        </form>
        {tipo === "formula" && <p className="mudo">Para anidar, primero creá la fórmula interna como métrica y después usala como operando de otra.</p>}
      </details>
    </section>
  );
}

function CampoOperando({
  etiqueta,
  tipo,
  onTipo,
  metricaId,
  onMetricaId,
  numero,
  onNumero,
  metricas,
}: {
  etiqueta: string;
  tipo: "metrica" | "numero";
  onTipo: (tipo: "metrica" | "numero") => void;
  metricaId: string;
  onMetricaId: (id: string) => void;
  numero: string;
  onNumero: (numero: string) => void;
  metricas: MetricaModelo[];
}) {
  return (
    <span className={estilos.operando}>
      <select className="campo" value={tipo} onChange={(e) => onTipo(e.target.value as "metrica" | "numero")}>
        <option value="metrica">Métrica</option>
        <option value="numero">Número</option>
      </select>
      {tipo === "metrica" ? (
        <select className="campo" value={metricaId} onChange={(e) => onMetricaId(e.target.value)} required>
          <option value="">{etiqueta}…</option>
          {metricas.map((m) => (
            <option key={m.id} value={m.id}>
              {m.nombre}
            </option>
          ))}
        </select>
      ) : (
        <input className="campo" type="number" step="any" placeholder={etiqueta} value={numero} onChange={(e) => onNumero(e.target.value)} required />
      )}
    </span>
  );
}

function SeccionDimensionesTiempo({ modelo, aplicar, pendiente }: { modelo: ModeloSemantico; aplicar: Aplicar; pendiente: boolean }) {
  const campos = todosLosCampos(modelo).filter((campo) => campo.tipoDato === "fecha" || campo.tipoDato === "fecha_hora");
  const [campo, setCampo] = useState("");
  const [granularidades, setGranularidades] = useState<Granularidad[]>([...GRANULARIDADES]);

  return (
    <section className={estilos.seccion}>
      <h2>Dimensiones de tiempo</h2>
      {modelo.dimensiones_tiempo.length === 0 && <p className="mudo">Ninguna todavía.</p>}
      <ul className={estilos.listaDimensiones}>
        {modelo.dimensiones_tiempo.map((dimension) => (
          <li key={dimension.campo}>
            <span className="codigo">{dimension.campo}</span>
            <span className="mudo">{dimension.granularidades.join(", ")}</span>
            <button type="button" className="boton boton--chico boton--peligro" disabled={pendiente} onClick={() => aplicar({ operacion: "quitar_dimension_tiempo", campo: dimension.campo })}>
              Quitar
            </button>
          </li>
        ))}
      </ul>
      <details className={estilos.crear}>
        <summary>Agregar una dimensión de tiempo</summary>
        <form
          className={estilos.formCrear}
          onSubmit={(e) => {
            e.preventDefault();
            if (!campo) return;
            void aplicar({ operacion: "agregar_dimension_tiempo", campo, granularidades });
          }}
        >
          <select className="campo" value={campo} onChange={(e) => setCampo(e.target.value)} required>
            <option value="">Campo de fecha…</option>
            {campos.map((c) => (
              <option key={c.referencia} value={c.referencia}>
                {c.etiqueta}
              </option>
            ))}
          </select>
          <div className={estilos.checkboxes}>
            {GRANULARIDADES.map((g) => (
              <label key={g} className={estilos.checkbox}>
                <input
                  type="checkbox"
                  checked={granularidades.includes(g)}
                  onChange={(e) => setGranularidades((actuales) => (e.target.checked ? [...actuales, g] : actuales.filter((x) => x !== g)))}
                />
                {g}
              </label>
            ))}
          </div>
          <button type="submit" className="boton boton--primario boton--chico" disabled={pendiente || granularidades.length === 0}>
            Agregar
          </button>
        </form>
      </details>
    </section>
  );
}
