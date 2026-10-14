import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // host "127.0.0.1" garante bind em IPv4 — no Windows, "localhost" às
    // vezes resolve para IPv4 primeiro, e o default do Vite (IPv6 ::1) não
    // responderia. Assim http://localhost:5173 e http://127.0.0.1:5173 funcionam.
    host: "127.0.0.1",
    port: 5173,
    strictPort: false,
  },
});
