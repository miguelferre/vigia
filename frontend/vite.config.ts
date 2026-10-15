import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import fs from "node:fs";
import path from "node:path";

// Tema por build. `VITE_TEMA=miguel` deja solo la estética
// personal: el módulo de estéticas extra se resuelve al registro vacío y el
// CSS de las privadas no entra en el grafo del bundle. Sin la variable (o con
// `todos`) se usa `temas-privados.ts` si existe; en el árbol público no existe
// y el resultado es el mismo que con `miguel`.
const temaBuild = process.env.VITE_TEMA ?? "todos";
const temasPrivados = path.resolve(import.meta.dirname, "./src/themes/temas-privados.ts");
const temasExtra =
  temaBuild !== "miguel" && fs.existsSync(temasPrivados)
    ? temasPrivados
    : path.resolve(import.meta.dirname, "./src/themes/temas-extra.ts");

// Marca del tema con el que se compiló el estático: `<meta name="vigia-tema">`
// en `index.html`. La leen el test de empaquetado y `build/build.py`.
const marcaTema = {
  name: "vigia-tema-marca",
  transformIndexHtml: () => [
    { tag: "meta", attrs: { name: "vigia-tema", content: temaBuild }, injectTo: "head" as const },
  ],
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), marcaTema],
  resolve: {
    alias: [
      { find: /^@\/themes\/temas-extra$/, replacement: temasExtra },
      { find: "@", replacement: path.resolve(import.meta.dirname, "./src") },
    ],
  },
  build: {
    outDir: "../src/vigia/static",
    emptyOutDir: true,
    // Se parte el chunk único. Las pantallas ya van por
    // separado con React.lazy; aquí se aíslan las tres librerías pesadas para
    // que ninguna pieza pase de 400 KB.
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes("node_modules")) return undefined;
          if (/[\\/]node_modules[\\/](recharts|victory-vendor|d3-)/.test(id)) return "recharts";
          if (/[\\/]node_modules[\\/](react-router|@tanstack)[\\/]/.test(id)) return "router";
          if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(id)) return "react";
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: process.env.VIGIA_API ?? "http://127.0.0.1:8790",
        changeOrigin: true,
        // SSE a través del proxy de desarrollo. http-proxy llama a `writeHead`,
        // pero Node no manda la cabecera por el socket hasta el primer `write`:
        // en `/api/events/stream` el primer byte puede tardar lo que tarde el
        // latido (`sse_heartbeat_s`, 15 s), así que `EventSource` no abría, la
        // cabecera se quedaba en "Sin señal" y el diario no resaltaba el evento
        // recién llegado. Se fuerza el envío de la cabecera en el tick siguiente
        // al `proxyRes` (http-proxy la escribe justo después de emitirlo) para
        // las respuestas `text/event-stream`. En producción el estático lo sirve
        // el propio backend, mismo origen y sin proxy: esto es solo de dev.
        configure(proxy) {
          proxy.on("proxyRes", (proxyRes, _req, res) => {
            const tipo = String(proxyRes.headers["content-type"] ?? "");
            if (!tipo.includes("text/event-stream")) return;
            setImmediate(() => {
              if (!res.headersSent && !res.writableEnded) res.flushHeaders();
            });
          });
        },
      },
    },
  },
});
