import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Built files are served by function_app.py under /api/static/, the page itself under /api/phone, /api/dashboard, /api/map.
export default defineConfig({ plugins: [react()], base: "/api/static/" });
