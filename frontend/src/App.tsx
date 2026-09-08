import type { ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";

import { Cargando } from "./compartido/componentes/Cargando";
import { ProveedorSesion, rutaInicial, useSesion } from "./compartido/sesion";
import { Fuentes } from "./constructor/Fuentes";
import { Modelo } from "./constructor/Modelo";
import { Ingresar } from "./paginas/Ingresar";
import { Plataforma } from "./plataforma/Plataforma";
import type { Rol } from "./tipos";
import { Tablero } from "./visualizador/Tablero";

function Protegida({ roles, children }: { roles: Rol[]; children: ReactNode }) {
  const { usuario, cargando } = useSesion();
  if (cargando) return <Cargando texto="Abriendo UBoard…" />;
  if (!usuario) return <Navigate to="/ingresar" replace />;
  if (!roles.includes(usuario.rol)) return <Navigate to={rutaInicial(usuario)} replace />;
  return <>{children}</>;
}

function Inicio() {
  const { usuario, cargando } = useSesion();
  if (cargando) return <Cargando texto="Abriendo UBoard…" />;
  return <Navigate to={usuario ? rutaInicial(usuario) : "/ingresar"} replace />;
}

export function App() {
  return (
    <ProveedorSesion>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Inicio />} />
          <Route path="/ingresar" element={<Ingresar />} />
          <Route
            path="/tablero"
            element={
              <Protegida roles={["constructor", "visualizador"]}>
                <Tablero />
              </Protegida>
            }
          />
          <Route
            path="/fuentes"
            element={
              <Protegida roles={["constructor"]}>
                <Fuentes />
              </Protegida>
            }
          />
          <Route
            path="/modelo"
            element={
              <Protegida roles={["constructor"]}>
                <Modelo />
              </Protegida>
            }
          />
          <Route
            path="/plataforma"
            element={
              <Protegida roles={["plataforma"]}>
                <Plataforma />
              </Protegida>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </ProveedorSesion>
  );
}
