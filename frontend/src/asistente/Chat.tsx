/* Chat del asistente (fase 3, pasos 19 a 21): un solo componente para las
   dos interfaces del §1 de la especificacion. `variante="flotante"` es el
   chat de escritura del constructor (boton + panel que se abre y cierra,
   montado una sola vez en Marco, disponible en cualquier pantalla).
   `variante="inline"` es el cuadro de preguntas del Tablero, para
   constructor y visualizador, siempre visible cerca de los filtros y que
   les manda como `filtros` (paso 21) para que la respuesta los respete.
   En los dos casos cada pedido es independiente: el backend no persiste la
   conversacion (decidido en la fase 3), asi que el historial que se ve
   aca vive solo en el estado de esta pantalla y se pierde al refrescar. */
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { mensajeDeError, pedir, rutaWorkspace } from "../compartido/api";
import { Cargando } from "../compartido/componentes/Cargando";
import { useSesion } from "../compartido/sesion";
import type { FiltrosActivos, RespuestaAsistente } from "../tipos";
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
  if (herramienta === "consultar" || herramienta === "restaurar_version") return null;
  return OPERACIONES_DASHBOARD.has(herramienta) ? { to: "/tablero", texto: "Ver en el Tablero" } : { to: "/modelo", texto: "Ver en Modelo" };
}

interface MensajeChat {
  id: number;
  rol: "usuario" | "asistente" | "error";
  texto: string;
  acciones?: { herramienta: string; resultado: string }[];
}

interface Props {
  variante?: "flotante" | "inline";
  filtrosActivos?: FiltrosActivos;
}

export function Chat({ variante = "flotante", filtrosActivos }: Props) {
  const { usuario } = useSesion();
  const workspaceId = usuario?.workspace_id ?? 0;
  const esVisualizador = usuario?.rol === "visualizador";
  const clienteConsultas = useQueryClient();
  const [abierto, setAbierto] = useState(false);
  const [texto, setTexto] = useState("");
  const [mensajes, setMensajes] = useState<MensajeChat[]>([]);
  const proximoId = useRef(0);
  const finRef = useRef<HTMLDivElement>(null);

  const agregarMensaje = (mensaje: Omit<MensajeChat, "id">) => {
    proximoId.current += 1;
    setMensajes((previos) => [...previos, { ...mensaje, id: proximoId.current }]);
  };

  const enviar = useMutation({
    mutationFn: (mensaje: string) =>
      pedir<RespuestaAsistente>(rutaWorkspace(workspaceId, "/asistente/mensajes"), {
        method: "POST",
        json: filtrosActivos && Object.keys(filtrosActivos).length > 0 ? { mensaje, filtros: filtrosActivos } : { mensaje },
      }),
    onSuccess: (respuesta) => {
      agregarMensaje({ rol: "asistente", texto: respuesta.texto, acciones: respuesta.acciones });
      if (respuesta.acciones.length > 0) {
        for (const artefacto of ["modelo", "dashboard"]) {
          void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId] });
          void clienteConsultas.invalidateQueries({ queryKey: [artefacto, workspaceId, "versiones"] });
        }
      }
    },
    onError: (error) => agregarMensaje({ rol: "error", texto: mensajeDeError(error) }),
  });

  // Dictado por voz (Web Speech API): sin backend, solo llena el campo de
  // texto, la persona revisa y envia como siempre. Sin soporte del
  // navegador (Firefox, Safari en iOS), el boton de microfono no aparece.
  const ConstructorVoz = useMemo(() => obtenerConstructorDeVoz(), []);
  const [escuchando, setEscuchando] = useState(false);
  const reconocimientoRef = useRef<ReconocimientoVoz | null>(null);

  useEffect(() => () => reconocimientoRef.current?.stop(), []);

  const alternarMicrofono = () => {
    if (escuchando) {
      reconocimientoRef.current?.stop();
      setEscuchando(false);
      return;
    }
    if (!ConstructorVoz) return;
    const reconocimiento = new ConstructorVoz();
    reconocimiento.lang = "es-AR";
    reconocimiento.interimResults = true;
    reconocimiento.continuous = false;
    reconocimiento.onresult = (evento) => setTexto(transcriptoDe(evento));
    reconocimiento.onerror = () => setEscuchando(false);
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
    const valor = texto.trim();
    if (!valor || enviar.isPending) return;
    agregarMensaje({ rol: "usuario", texto: valor });
    setTexto("");
    enviar.mutate(valor);
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
            aria-label={escuchando ? "Detener el dictado por voz" : "Preguntar por voz"}
            title={escuchando ? "Detener el dictado" : "Preguntar por voz"}
          >
            🎤
          </button>
        )}
        <button type="submit" className="boton boton--primario boton--chico" disabled={enviar.isPending || !texto.trim()}>
          {esVisualizador || variante === "inline" ? "Preguntar" : "Enviar"}
        </button>
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
        {abierto ? "✕ Cerrar" : "💬 Asistente"}
      </button>
      {abierto && (
        <aside className={estilos.panel} aria-label="Asistente de UBoard">
          <header className={estilos.cabecera}>
            <strong>Asistente</strong>
            <span className="mudo">Pedile cambios en lenguaje natural</span>
          </header>
          {contenido}
        </aside>
      )}
    </>
  );
}
