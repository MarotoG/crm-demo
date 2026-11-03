import react from "@vitejs/plugin-react";
// defineConfig de vitest/config: la misma configuración de Vite más la sección test.
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // En desarrollo, el navegador solo habla con Vite (5173) y Vite reenvía /api
    // a la API (8000). Así hay un único origen, como tras nginx en producción,
    // y no hace falta configurar CORS.
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  test: {
    // Las pruebas (Vitest + Testing Library) usan un DOM simulado y una API falsa:
    // no necesitan el backend ni el navegador.
    environment: "jsdom",
    setupFiles: ["./src/configuracionPruebas.ts"],
  },
});
