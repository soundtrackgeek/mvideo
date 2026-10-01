import { defineConfig } from "vite";
export default defineConfig({
  base: "/studio/",
  build: { outDir: "../../server/mvideo/web", emptyOutDir: true },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/image": "http://127.0.0.1:8765",
    },
  },
});
