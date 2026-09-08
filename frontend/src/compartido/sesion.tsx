/* Sesion: quien esta logueado, segun /api/auth/yo. La cookie la maneja el
   navegador; aca solo se cachea el usuario y se reacciona al 401. */
import { createContext, useCallback, useContext, useEffect, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { Usuario } from "../tipos";
import { ErrorApi, EVENTO_SESION_VENCIDA, pedir } from "./api";

interface Sesion {
  usuario: Usuario | null;
  cargando: boolean;
  iniciar: (email: string, clave: string) => Promise<Usuario>;
  cerrar: () => Promise<void>;
}

const ContextoSesion = createContext<Sesion | null>(null);
export const CLAVE_YO = ["yo"] as const;

export function ProveedorSesion({ children }: { children: ReactNode }) {
  const clienteConsultas = useQueryClient();
  const consulta = useQuery({
    queryKey: CLAVE_YO,
    queryFn: async () => {
      try {
        return await pedir<Usuario>("/api/auth/yo");
      } catch (error) {
        if (error instanceof ErrorApi && error.estado === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
    retry: false,
  });

  useEffect(() => {
    const vencida = () => {
      clienteConsultas.setQueryData(CLAVE_YO, null);
    };
    window.addEventListener(EVENTO_SESION_VENCIDA, vencida);
    return () => window.removeEventListener(EVENTO_SESION_VENCIDA, vencida);
  }, [clienteConsultas]);

  // Al cambiar de usuario se descarta todo lo cacheado MENOS la consulta "yo":
  // borrarla con clear() deja al observador de useQuery apuntando a una
  // consulta muerta y la app cree que no hay sesion aunque el login haya
  // salido bien (paso 7, encontrado probando el login en el navegador).
  const olvidarDatosDeOtroUsuario = useCallback(() => {
    clienteConsultas.removeQueries({ predicate: (consulta) => consulta.queryKey[0] !== CLAVE_YO[0] });
  }, [clienteConsultas]);

  const iniciar = useCallback(
    async (email: string, clave: string) => {
      const usuario = await pedir<Usuario>("/api/auth/login", { method: "POST", json: { email, clave } });
      olvidarDatosDeOtroUsuario();
      clienteConsultas.setQueryData(CLAVE_YO, usuario);
      return usuario;
    },
    [clienteConsultas, olvidarDatosDeOtroUsuario],
  );

  const cerrar = useCallback(async () => {
    await pedir("/api/auth/logout", { method: "POST" });
    olvidarDatosDeOtroUsuario();
    clienteConsultas.setQueryData(CLAVE_YO, null);
  }, [clienteConsultas, olvidarDatosDeOtroUsuario]);

  return (
    <ContextoSesion.Provider value={{ usuario: consulta.data ?? null, cargando: consulta.isPending, iniciar, cerrar }}>
      {children}
    </ContextoSesion.Provider>
  );
}

export function useSesion(): Sesion {
  const sesion = useContext(ContextoSesion);
  if (!sesion) throw new Error("useSesion fuera de ProveedorSesion");
  return sesion;
}

/** Donde arranca cada rol despues del login. */
export function rutaInicial(usuario: Usuario): string {
  return usuario.rol === "plataforma" ? "/plataforma" : "/tablero";
}
