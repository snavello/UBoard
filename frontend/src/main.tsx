import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { App } from "./App";

// Un solo cliente de consultas para toda la app. Los datos del dashboard se
// cachean por clave (endpoint + filtros activos), asi que dos paneles que
// piden lo mismo comparten la respuesta.
const clienteConsultas = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
});

createRoot(document.getElementById("raiz")!).render(
  <StrictMode>
    <QueryClientProvider client={clienteConsultas}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
