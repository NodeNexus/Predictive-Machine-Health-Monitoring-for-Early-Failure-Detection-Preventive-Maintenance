import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    // Listen on IPv4 loopback only. Vite's default ("localhost") can resolve to IPv6 ::1 only on Windows,
    // which makes http://127.0.0.1:5173 refuse connections; browsers still reach this via http://localhost:5173.
    host: '127.0.0.1',
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/ws': {
        target: 'ws://127.0.0.1:8000',
        ws: true,
      },
    },
  },
})
