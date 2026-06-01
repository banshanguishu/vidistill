import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // 显式用 127.0.0.1 而非 localhost：Windows 上 Node 可能把 localhost 解析为
      // IPv6 ::1，而 uvicorn 默认只监听 IPv4 127.0.0.1，会导致代理连不上后端。
      '/jobs': 'http://127.0.0.1:8000',
      '/my': 'http://127.0.0.1:8000',
      '/feedback': 'http://127.0.0.1:8000',
    },
  },
  build: { outDir: 'dist' },
})
