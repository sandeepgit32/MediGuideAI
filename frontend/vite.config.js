import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/auth': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
      '/session': {
        target: 'http://backend:8000',
        changeOrigin: true,
      },
    },
  },
})

