import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
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
