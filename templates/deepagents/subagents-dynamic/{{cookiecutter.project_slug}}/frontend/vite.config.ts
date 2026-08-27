import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: process.env.FRONTEND_HOST ?? "127.0.0.1",
    port: Number(process.env.FRONTEND_PORT ?? "{{ cookiecutter.frontend_port }}"),
  },
});
