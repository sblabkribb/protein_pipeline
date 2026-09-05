import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "vite";
import tailwindcss from "@tailwindcss/vite";

const __dirname = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [tailwindcss()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      // guided.html 은 index.html 과 독립된 최소 화면이다. 여기 나열하지 않으면
      // vite 가 index.html 만 빌드해서 배포본에서 빠진다.
      input: {
        main: resolve(__dirname, "index.html"),
        guided: resolve(__dirname, "guided.html"),
      },
    },
  },
  server: {
    host: "127.0.0.1",
  },
  preview: {
    host: "127.0.0.1",
  },
});
