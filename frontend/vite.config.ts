import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Сборка кладётся в backend/static: приложение и API отдаются одним процессом
// и одним портом, поэтому нет ни CORS, ни переменной с адресом API.
// В dev-режиме /api проксируется на backend — путь в коде остаётся тем же.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: '../backend/static',
    emptyOutDir: true,
    sourcemap: true,
  },
})
