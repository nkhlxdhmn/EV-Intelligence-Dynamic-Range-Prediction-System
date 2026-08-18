import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build outputs to `frontend/dist`, which the FastAPI backend serves at
// `/dashboard/`. Relative base so the bundle works under any mount path.
export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/model/info": "http://127.0.0.1:8000",
      "/predict": "http://127.0.0.1:8000",
      "/simulator": "http://127.0.0.1:8000",
      "/live": "http://127.0.0.1:8000",
    },
  },
});