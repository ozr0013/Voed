import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import path from "path";

// Dev server proxies API + WebSocket traffic to the FastAPI backend so the
// browser only ever talks to one origin. `host: true` exposes the dev server on
// the LAN for teammates/judges.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
