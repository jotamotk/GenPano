import { createServer } from "vite";
import react from "@vitejs/plugin-react";

const server = await createServer({
  configFile: false,
  root: process.cwd(),
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    open: false,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/admin/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        secure: false,
      },
    },
  },
  build: {
    rollupOptions: {
      external: (id) => id.includes("__ci_fixtures__"),
    },
  },
});

await server.listen();
server.printUrls();
setInterval(() => {}, 2 ** 30);
