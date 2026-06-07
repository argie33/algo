#!/usr/bin/env node

import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

console.log('🔍 DIRECT API CALL TEST IN BROWSER\n');
console.log('=' .repeat(80) + '\n');

try {
  // Navigate to app to get API configured
  await page.goto('http://localhost:5173/app/markets', { waitUntil: 'networkidle' });

  // Now try calling the API directly from browser context
  const result = await page.evaluate(async () => {
    console.log('[Test] About to call API...');

    try {
      // Get axios instance from global scope if available, or fetch
      const response = await fetch('http://localhost:3001/api/algo/swing-scores?limit=10&min_score=0');
      console.log(`[Test] Response status: ${response.status}`);

      const body = await response.json();
      console.log(`[Test] Response keys: ${Object.keys(body).join(', ')}`);
      console.log(`[Test] Items count: ${body.items ? body.items.length : 'N/A'}`);

      return {
        status: response.status,
        hasItems: !!body.items,
        itemsCount: body.items ? body.items.length : 0,
        keys: Object.keys(body),
      };
    } catch (err) {
      console.error(`[Test] API call failed:`, err.message);
      return { error: err.message };
    }
  });

  console.log('Result from browser context:');
  console.log(JSON.stringify(result, null, 2));

  // Now try with axios (which the app uses)
  console.log('\n' + '=' .repeat(80) + '\n');
  console.log('Testing with axios (as used in app)...\n');

  const axiosResult = await page.evaluate(async () => {
    try {
      // Check if axios is available in window
      if (typeof window.axios === 'undefined') {
        // Import from a module
        const response = await fetch('http://localhost:3001/api/algo/swing-scores?limit=10');
        const data = await response.json();
        return { success: true, itemCount: data.items?.length || 0 };
      }

      // Use window.axios
      const response = await window.axios.get('http://localhost:3001/api/algo/swing-scores?limit=10');
      console.log(`[Axios] Status: ${response.status}`);
      console.log(`[Axios] Items: ${response.data?.items?.length}`);

      return { success: true, itemCount: response.data?.items?.length };
    } catch (err) {
      console.error(`[Axios Error]:`, err.message);
      return { success: false, error: err.message };
    }
  });

  console.log('Axios result:');
  console.log(JSON.stringify(axiosResult, null, 2));

} catch (err) {
  console.error('Error:', err);
}

console.log('\n' + '=' .repeat(80) + '\n');

await browser.close();
