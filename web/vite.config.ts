import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// defineConfig from vitest/config so `test` key type-checks (codex IMPORTANT-5).
// VITE_BASE lets the GH Pages workflow inject /llm-poker-arena/ at build time;
// dev uses the default '/'.
export default defineConfig({
  base: process.env.VITE_BASE ?? '/',
  plugins: [react()],
  test: {
    environment: 'happy-dom',
    globals: true,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
