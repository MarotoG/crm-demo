import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

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
});
