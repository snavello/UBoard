/* Chat del constructor (fase 3, paso 19-20): un panel que se abre y cierra,
   disponible en cualquier pantalla del constructor (esta montado en Marco).
   Cada pedido es independiente: el backend no persiste la conversacion
   (decidido en la fase 3), asi que el historial que se ve aca vive solo en
   esta pestania y se pierde al refrescar. */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { mensajeDeError, pedir, rutaWorkspace } from "../compartido/api";
import { Cargando } from "../compartido/componentes/Cargando";
import { useSesion } from "../compartido/sesion";
import type { RespuestaAsistente } from "../tipos";
import estilos from "./Chat.module.css";

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

export function Chat() {
  const { usuario } = useSesion();
  const workspaceId = usuario?.workspace_id ?? 0;
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
    mutationFn: (mensaje: string) => pedir<RespuestaAsistente>(rutaWorkspace(workspaceId, "/asistente/mensajes"), { method: "POST", json: { mensaje } }),
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

  useEffect(() => {
    if (abierto) finRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensajes, enviar.isPending, abierto]);

  const enviarMensaje = (evento: React.FormEvent) => {
    evento.preventDefault();
    const valor = texto.trim();
    if (!valor || enviar.isPending) return;
    agregarMensaje({ rol: "usuario", texto: valor });
    setTexto("");
    enviar.mutate(valor);
  };

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
          <div className={estilos.mensajes}>
            {mensajes.length === 0 && (
              <p className={`mudo ${estilos.vacio}`}>
                Por ejemplo: "agregá un gráfico de ventas por sucursal" o "creá una métrica margen que sea ventas menos costos".
              </p>
            )}
            {mensajes.map((mensaje) => (
              <div key={mensaje.id} className={`${estilos.mensaje} ${estilos[mensaje.rol]}`}>
                <p>{mensaje.texto}</p>
                {mensaje.acciones?.map((accion, indice) => {
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
              placeholder="Pedile algo al asistente…"
              value={texto}
              onChange={(evento) => setTexto(evento.target.value)}
              disabled={enviar.isPending}
              aria-label="Mensaje para el asistente"
            />
            <button type="submit" className="boton boton--primario boton--chico" disabled={enviar.isPending || !texto.trim()}>
              Enviar
            </button>
          </form>
        </aside>
      )}
    </>
  );
}
