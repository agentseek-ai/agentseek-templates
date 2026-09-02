import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return { plugins: [react()], server: { host: env.FRONTEND_HOST || "127.0.0.1", port: Number(env.FRONTEND_PORT || "{{ cookiecutter.frontend_port }}"), strictPort: true } };
});
