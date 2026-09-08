import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// En desarrollo Vite sirve el frontend en 5173 y reenvia /api al backend
// (uvicorn en 8000). En produccion el build va a backend/app/estatico/ y lo
// sirve FastAPI desde el mismo origen: sin CORS y sin proxy.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "../backend/app/estatico",
    emptyOutDir: true,
  },
});
