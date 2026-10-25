import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.js',
    // Tests never depend on a local frontend/.env: no bot check unless a test stubs a key.
    env: { VITE_TURNSTILE_SITE_KEY: '' },
  },
})
