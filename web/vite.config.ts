import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The dev server proxies /api so the frontend has no notion of a backend host.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.SARAI_API_URL ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
