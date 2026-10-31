import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// FastAPI backend; ADTRACE_API overrides it (the screenshot task runs its own backend on another port).
const api = process.env.ADTRACE_API ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': api },
  },
  preview: {
    proxy: { '/api': api },
  },
});
