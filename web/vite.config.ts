import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:7071", changeOrigin: true } },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
});
