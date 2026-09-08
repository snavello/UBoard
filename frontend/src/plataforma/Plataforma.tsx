/* Admin de plataforma: organizaciones, sus usuarios y los administradores. */
import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pedir } from "../compartido/api";
import { AvisoError } from "../compartido/componentes/Aviso";
import { Cargando } from "../compartido/componentes/Cargando";
import { Marco } from "../compartido/componentes/Marco";
import { formatearFecha } from "../compartido/formato";
import { useSesion } from "../compartido/sesion";
import type { OrganizacionPlataforma, Usuario } from "../tipos";
import estilos from "./Plataforma.module.css";

const BASE = "/api/plataforma";

export function Plataforma() {
  const { usuario } = useSesion();
  const [seleccionada, setSeleccionada] = useState<number | null>(null);
  const organizaciones = useQuery({ queryKey: ["plataforma", "organizaciones"], queryFn: () => pedir<OrganizacionPlataforma[]>(`${BASE}/organizaciones`) });
  const organizacion = organizaciones.data?.find((o) => o.id === seleccionada) ?? null;

  return (
    <Marco kicker="UBoard · Plataforma" titulo="Organizaciones y usuarios">
      <div className={estilos.pagina}>
        <section className={estilos.seccion}>
          <div className={estilos.cabeceraSeccion}>
            <h2>Organizaciones</h2>
            <FormularioOrganizacion />
          </div>
          {organizaciones.isPending && <Cargando />}
          {organizaciones.isError && <AvisoError error={organizaciones.error} />}
          {organizaciones.data && (
            <table className="tabla">
              <thead>
                <tr>
                  <th>Nombre</th>
                  <th className="numero">Usuarios</th>
                  <th>Estado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {organizaciones.data.map((o) => (
                  <tr key={o.id} className={o.id === seleccionada ? estilos.filaActiva : undefined}>
                    <td>
                      <button type="button" className={estilos.enlace} onClick={() => setSeleccionada(o.id)}>
                        {o.nombre}
                      </button>
                    </td>
                    <td className="numero">{o.cantidad_usuarios}</td>
                    <td>
                      <span className={`pastilla ${o.activa ? "pastilla--exito" : "pastilla--peligro"}`}>{o.activa ? "activa" : "desactivada"}</span>
                    </td>
                    <td>
                      <AlternarOrganizacion organizacion={o} />
                    </td>
                  </tr>
                ))}
                {organizaciones.data.length === 0 && (
                  <tr>
                    <td colSpan={4} className="mudo">
                      Todavía no hay organizaciones.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </section>

        {organizacion && <UsuariosDeOrganizacion organizacion={organizacion} />}

        <section className={estilos.seccion}>
          <div className={estilos.cabeceraSeccion}>
            <h2>Administradores de plataforma</h2>
          </div>
          <Administradores yo={usuario} />
        </section>
      </div>
    </Marco>
  );
}

function usarInvalidar() {
  const clienteConsultas = useQueryClient();
  return () => void clienteConsultas.invalidateQueries({ queryKey: ["plataforma"] });
}

function FormularioOrganizacion() {
  const [nombre, setNombre] = useState("");
  const invalidar = usarInvalidar();
  const crear = useMutation({
    mutationFn: () => pedir<OrganizacionPlataforma>(`${BASE}/organizaciones`, { method: "POST", json: { nombre } }),
    onSuccess: () => {
      setNombre("");
      invalidar();
    },
  });
  return (
    <form
      className={estilos.formularioLinea}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        crear.mutate();
      }}
    >
      <input className="campo" placeholder="Nueva organización" value={nombre} onChange={(e) => setNombre(e.target.value)} required aria-label="Nombre de la organización" />
      <button className="boton boton--primario" type="submit" disabled={crear.isPending}>
        Crear
      </button>
      {crear.isError && <AvisoError error={crear.error} />}
    </form>
  );
}

function AlternarOrganizacion({ organizacion }: { organizacion: OrganizacionPlataforma }) {
  const invalidar = usarInvalidar();
  const cambiar = useMutation({
    mutationFn: () => pedir(`${BASE}/organizaciones/${organizacion.id}`, { method: "PATCH", json: { activa: !organizacion.activa } }),
    onSuccess: invalidar,
  });
  return (
    <button type="button" className="boton boton--chico" onClick={() => cambiar.mutate()} disabled={cambiar.isPending}>
      {organizacion.activa ? "Desactivar" : "Activar"}
    </button>
  );
}

function UsuariosDeOrganizacion({ organizacion }: { organizacion: OrganizacionPlataforma }) {
  const usuarios = useQuery({
    queryKey: ["plataforma", "usuarios", organizacion.id],
    queryFn: () => pedir<Usuario[]>(`${BASE}/organizaciones/${organizacion.id}/usuarios`),
  });
  return (
    <section className={estilos.seccion}>
      <div className={estilos.cabeceraSeccion}>
        <h2>Usuarios de {organizacion.nombre}</h2>
      </div>
      <FormularioUsuario ruta={`${BASE}/organizaciones/${organizacion.id}/usuarios`} conRol />
      {usuarios.isPending && <Cargando />}
      {usuarios.isError && <AvisoError error={usuarios.error} />}
      {usuarios.data && <TablaUsuarios usuarios={usuarios.data} />}
    </section>
  );
}

function Administradores({ yo }: { yo: Usuario | null }) {
  const administradores = useQuery({ queryKey: ["plataforma", "administradores"], queryFn: () => pedir<Usuario[]>(`${BASE}/administradores`) });
  return (
    <>
      <FormularioUsuario ruta={`${BASE}/administradores`} conRol={false} />
      {administradores.isPending && <Cargando />}
      {administradores.isError && <AvisoError error={administradores.error} />}
      {administradores.data && <TablaUsuarios usuarios={administradores.data} yo={yo} />}
    </>
  );
}

function FormularioUsuario({ ruta, conRol }: { ruta: string; conRol: boolean }) {
  const invalidar = usarInvalidar();
  const [datos, setDatos] = useState({ email: "", nombre: "", clave: "", rol: "constructor" });
  const crear = useMutation({
    mutationFn: () => pedir<Usuario>(ruta, { method: "POST", json: conRol ? datos : { email: datos.email, nombre: datos.nombre, clave: datos.clave } }),
    onSuccess: () => {
      setDatos({ email: "", nombre: "", clave: "", rol: "constructor" });
      invalidar();
    },
  });
  return (
    <form
      className={estilos.formularioUsuario}
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        crear.mutate();
      }}
    >
      <input className="campo" type="email" placeholder="Email" required value={datos.email} onChange={(e) => setDatos({ ...datos, email: e.target.value })} aria-label="Email" />
      <input className="campo" placeholder="Nombre" required value={datos.nombre} onChange={(e) => setDatos({ ...datos, nombre: e.target.value })} aria-label="Nombre" />
      <input className="campo" type="password" placeholder="Clave (8+ caracteres)" required minLength={8} value={datos.clave} onChange={(e) => setDatos({ ...datos, clave: e.target.value })} aria-label="Clave" autoComplete="new-password" />
      {conRol && (
        <select className="campo" value={datos.rol} onChange={(e) => setDatos({ ...datos, rol: e.target.value })} aria-label="Rol">
          <option value="constructor">constructor</option>
          <option value="visualizador">visualizador</option>
        </select>
      )}
      <button className="boton boton--primario" type="submit" disabled={crear.isPending}>
        Dar de alta
      </button>
      {crear.isError && <AvisoError error={crear.error} />}
    </form>
  );
}

function TablaUsuarios({ usuarios, yo }: { usuarios: Usuario[]; yo?: Usuario | null }) {
  const invalidar = usarInvalidar();
  const [error, setError] = useState<unknown>(null);
  const alternar = useMutation({
    mutationFn: (u: Usuario) => pedir(`${BASE}/usuarios/${u.id}`, { method: "PATCH", json: { activo: !u.activo } }),
    onSuccess: invalidar,
    onError: setError,
  });
  const nuevaClave = useMutation({
    mutationFn: ({ u, clave }: { u: Usuario; clave: string }) => pedir(`${BASE}/usuarios/${u.id}/clave`, { method: "POST", json: { clave } }),
    onSuccess: invalidar,
    onError: setError,
  });
  const pedirClave = (u: Usuario) => {
    const clave = window.prompt(`Nueva clave para ${u.email} (8 caracteres o más):`);
    if (clave) nuevaClave.mutate({ u, clave });
  };
  return (
    <>
      {error !== null && <AvisoError error={error} />}
      <table className="tabla">
        <thead>
          <tr>
            <th>Email</th>
            <th>Nombre</th>
            <th>Rol</th>
            <th>Último acceso</th>
            <th>Estado</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {usuarios.map((u) => (
            <tr key={u.id}>
              <td>{u.email}</td>
              <td>{u.nombre}</td>
              <td>
                <span className="pastilla">{u.rol}</span>
              </td>
              <td>{u.ultimo_acceso ? formatearFecha(u.ultimo_acceso) : "—"}</td>
              <td>
                <span className={`pastilla ${u.activo ? "pastilla--exito" : "pastilla--peligro"}`}>{u.activo ? "activo" : "desactivado"}</span>
              </td>
              <td className={estilos.accionesFila}>
                <button type="button" className="boton boton--chico" onClick={() => pedirClave(u)}>
                  Nueva clave
                </button>
                {yo?.id !== u.id && (
                  <button type="button" className="boton boton--chico" onClick={() => alternar.mutate(u)} disabled={alternar.isPending}>
                    {u.activo ? "Desactivar" : "Activar"}
                  </button>
                )}
              </td>
            </tr>
          ))}
          {usuarios.length === 0 && (
            <tr>
              <td colSpan={6} className="mudo">
                Sin usuarios.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}
