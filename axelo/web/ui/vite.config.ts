import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:7788',
      '/ws': { target: 'ws://localhost:7788', ws: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
