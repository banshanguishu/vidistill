import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/jobs': 'http://localhost:8000',
      '/my': 'http://localhost:8000',
      '/feedback': 'http://localhost:8000',
    },
  },
  build: { outDir: 'dist' },
})
