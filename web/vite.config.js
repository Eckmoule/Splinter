import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// En développement (`npm run dev`), les appels /api sont relayés vers l'API Python
// (`python -m splinter.dashboard --no-browser`, port 8050).
export default defineConfig({
  plugins: [vue()],
  build: { chunkSizeWarningLimit: 800 }, // appli locale : un seul fichier JS, ECharts compris
  server: {
    port: 5173,
    proxy: { '/api': 'http://127.0.0.1:8050' },
  },
})
