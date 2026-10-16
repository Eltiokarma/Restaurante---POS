import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// En desarrollo el panel llama a /api y Vite lo reenvía al servicio del
// estudio (uvicorn api:app --port 8001 desde estudio/).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:8001' } },
})
