import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './src/tests/integration/api-only',
  timeout: 45000,
  
  use: {
    // API testing doesn't require browsers
    baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
    ignoreHTTPSErrors: true,
    
    // API request options
    extraHTTPHeaders: {
      'Accept': 'application/json',
      'User-Agent': 'Playwright/API-Tests'
    },
  },
  
  projects: [
    {
      name: 'api-integration',
      testMatch: /.*\.test\.js/,
    },
  ],
  
  reporter: [
    ['line'],
    ['json', { outputFile: 'test-results/api-test-results.json' }]
  ],
  
  outputDir: 'test-results/api-artifacts',
});