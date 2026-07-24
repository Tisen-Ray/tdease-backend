import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import path from 'path'

export default defineConfig({
  plugins: [vue()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/tests/setup.ts'],
    // Exclude build artifacts, release output, and electron-side tests —
    // these either ship stale copies of test files or require the electron
    // runtime (node:test based .cjs specs), neither of which belongs in the
    // vitest dev suite.
    exclude: [
      '**/node_modules/**',
      '**/dist/**',
      '**/release/**',
      '**/build/**',
      '**/electron/**',
      '**/.{idea,git,cache,output,temp}/**',
    ],
    coverage: {
      provider: 'v8',
      thresholds: {
        branches: 30,
        functions: 40,
        lines: 45,
        statements: 45,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
