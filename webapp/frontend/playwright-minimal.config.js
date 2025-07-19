import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './src/tests',
  timeout: 30000,
  
  use: {
    headless: true,
    baseURL: 'https://d1zb7knau41vl9.cloudfront.net',
    ignoreHTTPSErrors: true,
    viewport: { width: 1280, height: 720 },
    actionTimeout: 10000,
    navigationTimeout: 15000,
  },
  
  projects: [
    {
      name: 'chromium-minimal',
      use: { 
        browserName: 'chromium',
        launchOptions: {
          args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        }
      },
    },
  ],
  
  reporter: 'line',
  outputDir: 'test-results/minimal',
});