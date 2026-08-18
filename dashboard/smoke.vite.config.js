import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    ssr: "./smoke-entry.jsx",
    outDir: ".smoke-out",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        format: "cjs",
        entryFileNames: "bundle.cjs",
      },
    },
  },
});
