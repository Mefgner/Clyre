import { fileURLToPath, URL } from 'node:url'
import Vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [Vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('web', import.meta.url)),
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests_frontend/vitest/**/*.test.ts'],
    setupFiles: ['tests_frontend/vitest/setup.ts'],
    // Vuetify ships per-component CSS that must go through the Vite pipeline
    // instead of native Node ESM.
    server: { deps: { inline: ['vuetify'] } },
  },
})
