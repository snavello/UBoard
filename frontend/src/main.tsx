import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { App } from "./App";
import { ErrorApi } from "./compartido/api";
import "./estilos/base.css";

// Un solo cliente de consultas para toda la app. Los datos del dashboard se
// cachean por clave (endpoint + filtros activos), asi que dos paneles que
// piden lo mismo comparten la respuesta. Los errores de negocio (4xx) no se
// reintentan: el mensaje ya dice que pasa.
const clienteConsultas = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (intentos, error) => !(error instanceof ErrorApi && error.estado < 500) && intentos < 2,
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={clienteConsultas}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
