import { chromium } from 'playwright';
import axios from 'axios';

const backend = 'http://localhost:3001';
const frontend = 'http://localhost:5190';

console.log('Checking dashboard data and display...\n');

// Test 1: Check API responses directly
console.log('=== TEST 1: API Responses ===');
try {
  const endpoints = [
    '/api/market-factors',
    '/api/market-factors/exposure',
    '/api/market-factors/market'
  ];

  for (const endpoint of endpoints) {
    try {
      const response = await axios.get(`${backend}${endpoint}`, { timeout: 5000 });
      console.log(`\n${endpoint}:`);

      if (response.data.factors) {
        const factors = response.data.factors;
        console.log(`  Found ${Object.keys(factors).length} factors`);

        // Check for critical factors
        for (const [key, data] of Object.entries(factors).slice(0, 5)) {
          console.log(`    - ${key}:`);
          if (data.value !== undefined) console.log(`        value: ${data.value}`);
          if (data.score !== undefined) console.log(`        score: ${data.score}`);
          if (data.error) console.log(`        ERROR: ${data.error}`);
        }
      } else if (Array.isArray(response.data)) {
        console.log(`  Array with ${response.data.length} items`);
        if (response.data[0]) {
          console.log(`  First item keys: ${Object.keys(response.data[0]).join(', ')}`);
        }
      } else {
        console.log(`  Status: ${JSON.stringify(response.data).substring(0, 100)}`);
      }
    } catch (e) {
      console.log(`  ✗ Error: ${e.message}`);
    }
  }
} catch (e) {
  console.log(`✗ API check failed: ${e.message}`);
}

// Test 2: Check dashboard rendering
console.log('\n\n=== TEST 2: Dashboard Rendering ===');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

try {
  console.log('Navigating to dashboard...');
  await page.goto(`${frontend}/app/algo-dashboard`, { waitUntil: 'domcontentloaded', timeout: 15000 });

  // Wait for initial load
  await page.waitForTimeout(3000);

  // Check if loading is complete
  const isLoading = await page.isVisible('text=Loading...');
  console.log(`  Page loading: ${isLoading ? 'YES' : 'NO'}`);

  // Check for error messages
  const errorMessages = await page.locator('[role="alert"]').allTextContents();
  if (errorMessages.length > 0) {
    console.log(`  Alert messages (${errorMessages.length}):`);
    errorMessages.forEach(msg => {
      if (msg.trim()) console.log(`    - ${msg.trim()}`);
    });
  }

  // Look for market factors panel
  const marketPanels = await page.locator('text=/Market|Exposure|Factors/i').allTextContents();
  console.log(`  Market-related panels: ${marketPanels.length}`);
  marketPanels.slice(0, 5).forEach(p => {
    if (p.trim()) console.log(`    - ${p.trim()}`);
  });

  // Check specific data displays
  const putCallText = await page.locator('text=/put.*call|ratio/i').allTextContents();
  console.log(`  Put/Call references: ${putCallText.length}`);
  putCallText.slice(0, 3).forEach(p => {
    if (p.trim()) console.log(`    - ${p.trim()}`);
  });

  // Get full page text to check for "Unavailable" or "N/A"
  const bodyText = await page.textContent('body');
  const unavailableCount = (bodyText.match(/Unavailable/gi) || []).length;
  const naCount = (bodyText.match(/\bN\/A\b/gi) || []).length;
  console.log(`  Unavailable markers: ${unavailableCount}`);
  console.log(`  N/A markers: ${naCount}`);

  // Take screenshot
  await page.screenshot({ path: 'dashboard-detailed.png', fullPage: true });
  console.log('\n✓ Screenshot saved to dashboard-detailed.png');

} catch (e) {
  console.error(`✗ Dashboard check failed: ${e.message}`);
} finally {
  await browser.close();
}

console.log('\n✓ Detailed check complete');
