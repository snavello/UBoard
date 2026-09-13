/* Chat del asistente (fase 3, pasos 19 a 21): un solo componente para las
   dos interfaces del §1 de la especificacion. `variante="flotante"` es el
   chat de escritura del constructor (boton + panel que se abre y cierra,
   montado una sola vez en Marco, disponible en cualquier pantalla).
   `variante="inline"` es el cuadro de preguntas del Tablero, para
   constructor y visualizador, siempre visible cerca de los filtros y que
   les manda como `filtros` (paso 21) para que la respuesta los respete.
   Nada de esto se persiste en el backend: el historial que se ve aca vive
   solo en el estado de esta pantalla y se pierde al refrescar, pero desde
   la fase 4 se le manda al backend como memoria corta de la conversacion
   (`historial`) para que una confirmacion corta ("sí, dale") a algo que el
   asistente propuso en el mensaje anterior tenga con que reconstruirse. */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { mensajeDeError, pedir, rutaWorkspace } from "../compartido/api";
import { Cargando } from "../compartido/componentes/Cargando";
import { useSesion } from "../compartido/sesion";
import type { AccionAsistente, FiltrosActivos, RespuestaAsistente } from "../tipos";
import estilos from "./Chat.module.css";
import { obtenerConstructorDeVoz, transcriptoDe, type ReconocimientoVoz } from "./vozWeb";

// Las 14 operaciones del dashboard (paso 16): un cambio de estas se ve en el
// Tablero; el resto de las operaciones (modelo) se ve en Modelo.
const OPERACIONES_DASHBOARD = new Set([
  "editar_titulo",
  "crear_filtro",
  "editar_filtro",
  "eliminar_filtro",
  "crear_kpi",
  "editar_kpi",
  "eliminar_kpi",
  "reordenar_kpis",
  "crear_grafico",
  "editar_grafico",
  "eliminar_grafico",
  "crear_pestania",
  "editar_pestania",
  "eliminar_pestania",
]);

function enlaceDe(herramienta: string): { to: string; texto: string } | null {
  if (herramienta === "consultar" || herramienta === "restaurar_version" || herramienta === "aplicar_filtro") return null;
  return OPERACIONES_DASHBOARD.has(herramienta) ? { to: "/tablero", texto: "Ver en el Tablero" } : { to: "/modelo", texto: "Ver en Modelo" };
}

interface MensajeChat {
  id: number;
  rol: "usuario" | "asistente" | "error" | "sistema";
  texto: string;
  acciones?: AccionAsistente[];
}

// Silencio (sin nuevo resultado de dictado) antes de mandar la pregunta sola.
const SILENCIO_PARA_AUTOENVIAR_MS = 4000;
// Turnos previos que se le mandan al backend como memoria corta (recorta
// igual del lado del servidor; esto es nomas para no mandar un historial
// larguisimo de una conversacion extensa).
const MAX_TURNOS_HISTORIAL = 6;

interface Props {
  variante?: "flotante" | "inline";
  filtrosActivos?: FiltrosActivos;
  // Click-to-filter (paso A de la fase 4): si el asistente aplica un
  // filtro que ya existe, esto lo refleja en el mismo estado que usan los
  // chips y el click en un grafico. Solo tiene sentido en el Tablero.
  onAplicarFiltro?: (filtroId: string, valor: unknown) => void;
}

export function Chat({ variante = "flotante", filtrosActivos, onAplicarFiltro }: Props) {
  const { usuario } = useSesion();
  const workspaceId = usuario?.workspace_id ?? 0;
  const esVisualizador = usuario?.rol === "visualizador";
  const clienteConsultas = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [mensajes, setMensajes] = useState<MensajeChat[]>([]);
  const mensajesRef = useRef<MensajeChat[]>([]);
  const proximoId = useRef(0);
  const finRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    mensajesRef.current = mensajes;
  }, [mensajes]);

  const agregarMensaje = (mensaje: Omit<MensajeChat, "id">) => {
    proximoId.current += 1;
    setMensajes((previos) => [...previos, { ...mensaje, id: proximoId.current }]);
  };

  const abortadorRef = useRef<AbortController | null>(null);

  const enviar = useMutation({
    mutationFn: (mensaje: string) => {
      // Via mensajesRef (no el estado "mensajes" directo) para no quedar con
      // un historial viejo si esto se llama desde un closure mas antiguo
      // (el auto-envio por voz dispara despues de un timer).
      const historial = mensajesRef.current
        .filter((previo): previo is MensajeChat & { rol: "usuario" | "asistente" } => previo.rol === "usuario" || previo.rol === "asistente")
        .slice(-MAX_TURNOS_HISTORIAL)
        .map((previo) => ({ rol: previo.rol, texto: previo.texto }));
      const abortador = new AbortController();
      abortadorRef.current = abortador;
      return pedir<RespuestaAsistente>(rutaWorkspace(workspaceId, "/asistente/mensajes"), {
        method: "POST",
        signal: abortador.signal,
        json: {
          mensaje,
          ...(historial.length > 0 && { historial }),
          ...(filtrosActivos && Object.keys(filtrosActivos).length > 0 && { filtros: filtrosActivos }),
        },
      });
    },
    onSuccess: (respuesta) => {
      agregarMensaje({ rol: "asistente", texto: respuesta.texto, acciones: respuesta.acciones });
      const artefactosTocados = respuesta.acciones.filter((accion) => accion.herramienta !== "aplicar_filtro");
      if (artefactosTocados.length > 0) {
        for (const artefacto of ["modelo", "dashboard"]) {
          void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId] });
          void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId, "versiones"] });
        }
      }
      for (const accion of respuesta.acciones) {
        if (accion.herramienta === "aplicar_filtro" && typeof accion.entrada.filtro === "string") {
          onAplicarFiltro?.(accion.entrada.filtro, accion.entrada.valor);
        }
      }
    },
    onError: (error) => {
      if (error instanceof DOMException && error.name === "AbortError") {
        agregarMensaje({ rol: "sistema", texto: "Cancelado." });
        return;
      }
      agregarMensaje({ rol: "error", texto: mensajeDeError(error) });
    },
  });

  const cancelarPedido = () => abortadorRef.current?.abort();

  const enviarTexto = (valor: string) => {
    const limpio = valor.trim();
    if (!limpio || enviar.isPending) return;
    agregarMensaje({ rol: "usuario", texto: limpio });
    setTexto("");
    enviar.mutate(limpio);
  };

  // Dictado por voz (Web Speech API): sin backend, solo llena el campo de
  // texto. Sin soporte del navegador (Firefox, Safari en iOS), el boton de
  // microfono no aparece. `continuous: true` para que no corte solo en una
  // pausa corta; el auto-envio despues de un silencio lo maneja este
  // componente con su propio timer, no la deteccion del navegador.
  const ConstructorVoz = useMemo(() => obtenerConstructorDeVoz(), []);
  const [escuchando, setEscuchando] = useState(false);
  const reconocimientoRef = useRef<ReconocimientoVoz | null>(null);
  const silencioRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const limpiarTimerDeSilencio = () => {
    if (silencioRef.current !== null) {
      clearTimeout(silencioRef.current);
      silencioRef.current = null;
    }
  };

  const detenerDictado = ({ conservarTexto }: { conservarTexto: boolean }) => {
    limpiarTimerDeSilencio();
    reconocimientoRef.current?.stop();
    reconocimientoRef.current = null;
    setEscuchando(false);
    if (!conservarTexto) setTexto("");
  };

  useEffect(() => () => detenerDictado({ conservarTexto: true }), []);

  const alternarMicrofono = () => {
    if (escuchando) {
      // El boton "Stop": corta el dictado y borra lo transcripto, porque si
      // la persona lo apreta a mano durante el dictado es porque algo salio
      // mal (si iba bien, el silencio lo manda solo).
      detenerDictado({ conservarTexto: false });
      return;
    }
    if (!ConstructorVoz) return;
    const reconocimiento = new ConstructorVoz();
    reconocimiento.lang = "es-AR";
    reconocimiento.interimResults = true;
    reconocimiento.continuous = true;
    reconocimiento.onresult = (evento) => {
      const nuevoTexto = transcriptoDe(evento);
      setTexto(nuevoTexto);
      limpiarTimerDeSilencio();
      silencioRef.current = setTimeout(() => {
        detenerDictado({ conservarTexto: true });
        enviarTexto(nuevoTexto);
      }, SILENCIO_PARA_AUTOENVIAR_MS);
    };
    reconocimiento.onerror = () => detenerDictado({ conservarTexto: true });
    reconocimiento.onend = () => setEscuchando(false);
    reconocimientoRef.current = reconocimiento;
    reconocimiento.start();
    setEscuchando(true);
  };

  const abiertoDeVerdad = variante === "inline" || abierto;

  useEffect(() => {
    if (abiertoDeVerdad) finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, enviar.isPending, abiertoDeVerdad]);

  const enviarMensaje = (evento: React.FormEvent) => {
    evento.preventDefault();
    enviarTexto(texto);
  };

  const vacio = esVisualizador
    ? 'Preguntale algo a tus datos, por ejemplo: "¿cuánto vendió Pérez en marzo?". Respeta los filtros activos.'
    : variante === "inline"
      ? 'Preguntale algo a tus datos (respeta los filtros activos), por ejemplo: "¿cuánto vendió Pérez en marzo?".'
      : 'Por ejemplo: "agregá un gráfico de ventas por sucursal" o "creá una métrica margen que sea ventas menos costos".';

  const contenido = (
    <>
      <div className={estilos.mensajes}>
        {mensajes.length === 0 && <p className={`mudo ${estilos.vacio}`}>{vacio}</p>}
        {mensajes.map((mensaje) => (
          <div key={mensaje.id} className={`${estilos.mensaje} ${estilos[mensaje.rol]}`}>
            <p>{mensaje.texto}</p>
            {mensaje.acciones
              ?.filter((accion) => accion.herramienta !== "consultar")
              .map((accion, indice) => {
                const enlace = enlaceDe(accion.herramienta);
                return (
                  <p key={indice} className={estilos.accion}>
                    ✓ {accion.resultado}
                    {enlace && (
                      <>
                        {" "}
                        <Link to={enlace.to} onClick={() => setAbierto(false)}>
                          {enlace.texto}
                        </Link>
                      </>
                    )}
                  </p>
                );
              })}
          </div>
        ))}
        {enviar.isPending && <Cargando chico texto="Pensando…" />}
        <div ref={finRef} />
      </div>
      <form className={estilos.formulario} onSubmit={enviarMensaje}>
        <input
          className="campo"
          placeholder={esVisualizador || variante === "inline" ? "Preguntale algo a tus datos…" : "Pedile algo al asistente…"}
          value={texto}
          onChange={(evento) => setTexto(evento.target.value)}
          disabled={enviar.isPending}
          aria-label="Mensaje para el asistente"
        />
        {ConstructorVoz && (
          <button
            type="button"
            className={`${estilos.botonMic} ${escuchando ? estilos.escuchando : ""}`}
            onClick={alternarMicrofono}
            disabled={enviar.isPending}
            aria-pressed={escuchando}
            aria-label={escuchando ? "Cancelar el dictado y borrar el texto" : "Preguntar por voz"}
            title={escuchando ? "Cancelar el dictado y borrar el texto" : "Preguntar por voz"}
          >
            {escuchando ? "⏹" : "🎤"}
          </button>
        )}
        {enviar.isPending ? (
          <button type="button" className="boton boton--peligro boton--chico" onClick={cancelarPedido}>
            Cancelar
          </button>
        ) : (
          <button type="submit" className="boton boton--primario boton--chico" disabled={!texto.trim()}>
            {esVisualizador || variante === "inline" ? "Preguntar" : "Enviar"}
          </button>
        )}
      </form>
    </>
  );

  if (variante === "inline") {
    return (
      <div className={estilos.inline} aria-label="Preguntale a tus datos">
        {contenido}
      </div>
    );
  }

  return (
    <>
      <button type="button" className={estilos.botonFlotante} onClick={() => setAbierto((valor) => !valor)} aria-expanded={abierto}>
        💬 Asistente
      </button>
      {abierto && (
        <aside className={estilos.panel} aria-label="Asistente de UBoard">
          <header className={estilos.cabecera}>
            <div className={estilos.cabeceraFila}>
              <strong>Asistente</strong>
              <button type="button" className={estilos.botonCerrar} onClick={() => setAbierto(false)} aria-label="Cerrar el asistente">
                ✕
              </button>
            </div>
            <span className="mudo">Pedile cambios en lenguaje natural</span>
          </header>
          {contenido}
        </aside>
      )}
    </>
  );
}
