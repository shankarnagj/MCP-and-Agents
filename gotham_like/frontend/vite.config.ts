/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.TESSERA_BACKEND ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": backend,
      "/ws": { target: backend.replace("http", "ws"), ws: true },
      "/health": backend,
    },
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": backend,
      "/ws": { target: backend.replace("http", "ws"), ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 2500,
    rollupOptions: {
      output: {
        manualChunks: { maplibre: ["maplibre-gl"], cytoscape: ["cytoscape"], echarts: ["echarts"] },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/setup.ts"],
  },
});
