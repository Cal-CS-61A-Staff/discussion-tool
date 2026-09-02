import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  // Pyodide is self-hosted under /pyodide/ (copied from node_modules by
  // scripts/copy-pyodide.mjs) and loaded at runtime by the grading worker
  // via a dynamic import of an absolute URL. Keep the bundler from trying
  // to resolve/inline it — same for the main bundle and the worker bundle.
  build: { rollupOptions: { external: [/^\/pyodide\//] } },
  worker: { rollupOptions: { external: [/^\/pyodide\//] } },
  server: {
    proxy: {
      '/api': {
        // 5050, not 5000 — macOS's AirPlay Receiver squats on 5000 by
        // default and will silently intercept requests meant for Flask.
        target: 'http://localhost:5050',
        changeOrigin: true,
      },
    },
  },
});
