import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Which port the API is on. 8000 by default; override when something else has
// already taken it - a stale server from a previous session holds the port
// open on Windows more often than it should, and the symptom is confusing
// (the interface loads but shows stale data from the old process).
//
//   $env:EVALNOVA_API_PORT = "8001"   # then npm run dev
const API_PORT = process.env.EVALNOVA_API_PORT ?? "8000";
const API = `http://127.0.0.1:${API_PORT}`;

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // The API is same-origin in development, so the browser never needs CORS
      // and the frontend never hard-codes a backend host.
      "/api": { target: API, changeOrigin: true },
      "/health": { target: API, changeOrigin: true },
    },
  },
});
