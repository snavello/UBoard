/* Cabecera editorial + navegacion por rol + pie con version. Envuelve todas
   las paginas con sesion. */
import type { ReactNode } from "react";
import { NavLink, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";

import type { Salud } from "../../tipos";
import { pedir } from "../api";
import { useSesion } from "../sesion";
import estilos from "./Marco.module.css";

interface Props {
  kicker?: string;
  titulo: string;
  acciones?: ReactNode;
  children: ReactNode;
}

export function Marco({ kicker, titulo, acciones, children }: Props) {
  const { usuario, cerrar } = useSesion();
  const navegar = useNavigate();
  const salud = useQuery({ queryKey: ["salud"], queryFn: () => pedir<Salud>("/api/salud"), staleTime: Infinity });

  const salir = async () => {
    await cerrar();
    navegar("/ingresar");
  };

  const esConstructor = usuario?.rol === "constructor";
  const esPlataforma = usuario?.rol === "plataforma";
  const organizacion = usuario?.organizacion?.nombre;

  return (
    <div className={estilos.pagina}>
      <header className={estilos.cabecera}>
        <div className={estilos.cabeceraInterior}>
          <div className={estilos.mancheta}>
            <span className="kicker">{kicker ?? (organizacion ? `UBoard · ${organizacion}` : "UBoard")}</span>
            <h1 className={estilos.titulo}>{titulo}</h1>
          </div>
          <nav className={estilos.navegacion} aria-label="Secciones">
            {!esPlataforma && (
              <NavLink to="/tablero" className={({ isActive }) => (isActive ? estilos.activa : undefined)}>
                Tablero
              </NavLink>
            )}
            {esConstructor && (
              <>
                <NavLink to="/fuentes" className={({ isActive }) => (isActive ? estilos.activa : undefined)}>
                  Fuentes
                </NavLink>
                <NavLink to="/modelo" className={({ isActive }) => (isActive ? estilos.activa : undefined)}>
                  Modelo
                </NavLink>
              </>
            )}
            {esPlataforma && (
              <NavLink to="/plataforma" className={({ isActive }) => (isActive ? estilos.activa : undefined)}>
                Plataforma
              </NavLink>
            )}
            <span className={estilos.usuario}>
              {usuario?.nombre}
              <button type="button" className="boton boton--texto boton--chico" onClick={salir}>
                Salir
              </button>
            </span>
          </nav>
        </div>
        {acciones && <div className={estilos.acciones}>{acciones}</div>}
      </header>
      <main className={estilos.contenido}>{children}</main>
      <footer className={estilos.pie}>
        {salud.data && salud.data.entorno !== "prod" && salud.data.entorno !== "demo" && (
          <span className="pastilla pastilla--advertencia">
            {salud.data.entorno} · v{salud.data.version}
          </span>
        )}
        <span className="mudo">UBoard</span>
      </footer>
    </div>
  );
}
