import { useQuery } from "@tanstack/react-query";

interface Salud {
  estado: string;
  version: string;
  entorno: string;
}

async function pedirSalud(): Promise<Salud> {
  const respuesta = await fetch("/api/salud");
  if (!respuesta.ok) {
    throw new Error(`El backend respondio ${respuesta.status}`);
  }
  return respuesta.json();
}

// Pantalla provisoria del paso 0: solo comprueba que el frontend compilado
// llega al backend. Se reemplaza por login y dashboard en el paso 7.
export function App() {
  const salud = useQuery({ queryKey: ["salud"], queryFn: pedirSalud });

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>UBoard</h1>
      <p>Un BI que se construye solo a partir de tus archivos.</p>
      {salud.isPending && <p>Consultando el backend...</p>}
      {salud.isError && <p>No se pudo hablar con el backend: {salud.error.message}</p>}
      {salud.isSuccess && (
        <p>
          Backend {salud.data.estado}, version {salud.data.version}, entorno {salud.data.entorno}.
        </p>
      )}
    </main>
  );
}
