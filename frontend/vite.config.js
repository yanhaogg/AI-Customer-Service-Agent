import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
export default defineConfig({
 plugins: [react()],
 server: { proxy: { '/api/activity': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/api/shop': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/api/catalog': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/api/admin': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/auth': { target: 'http://127.0.0.1:8000', changeOrigin: true } } },
 preview: { proxy: { '/api/activity': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/api/shop': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/api/catalog': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/api/admin': { target: 'http://127.0.0.1:8000', changeOrigin: true }, '/auth': { target: 'http://127.0.0.1:8000', changeOrigin: true } } },
})
