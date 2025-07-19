
import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./config/environments/test-setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      reportsDirectory: './reports/coverage',
      exclude: [
        'node_modules/',
        'test-results/',
        'reports/',
        'config/',
        '**/*.{test,spec}.{js,jsx,ts,tsx}'
      ],
      thresholds: {
        global: {
          statements: 85,
          branches: 80,
          functions: 85,
          lines: 85
        }
      }
    },
    testTimeout: 30000,
    hookTimeout: 10000
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, '../../../src'),
      '@tests': resolve(__dirname, '.')
    }
  }
});