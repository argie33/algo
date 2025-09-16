import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/tests/setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov', 'json'],
      reportsDirectory: './coverage',
      include: [
        'src/**/*.{js,jsx}',
        '!src/tests/**',
        '!src/**/*.test.*',
        '!src/**/*.spec.*'
      ],
      exclude: [
        'node_modules/**',
        'src/tests/**',
        'src/**/*.test.*',
        'src/**/*.spec.*',
        'src/main.jsx', // Entry point
        'src/vite-env.d.ts',
        '**/*.config.*',
        'dist/**',
        'coverage/**'
      ],
      thresholds: {
        global: {
          branches: 80,
          functions: 85,
          lines: 90,
          statements: 90
        },
        'src/components/**/*.jsx': {
          branches: 85,
          functions: 90,
          lines: 95,
          statements: 95
        },
        'src/services/**/*.js': {
          branches: 90,
          functions: 95,
          lines: 95,
          statements: 95
        }
      },
      watermarks: {
        statements: [80, 95],
        functions: [80, 95],
        branches: [80, 95],
        lines: [80, 95]
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
});