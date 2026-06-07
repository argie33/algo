#!/usr/bin/env node

import { chromium } from 'playwright';

const pages = [
  { url: 'http://localhost:5173/app/markets', name: 'Market Health' },
  { url: 'http://localhost:5173/app/sectors', name: 'Sector Analysis' },
  { url: 'http://localhost:5173/app/swing', name: 'Swing Candidates' },
  { url: 'http://localhost:5173/app/scores', name: 'Stock Scores' },
  { url: 'http://localhost:5173/app/portfolio', name: 'Portfolio' }
];

console.log('🔍 TESTING CORRECT ROUTES\n');
console.log('=' .repeat(80) + '\n');

const browser = await chromium.launch({ headless: true });

for (const pageInfo of pages) {
  const page = await browser.newPage();

  try {
    await page.goto(pageInfo.url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    const analysis = await page.evaluate(() => {
      const main = document.querySelector('main') || document.querySelector('[role="main"]');
      const allText = (main?.innerText || '').trim();

      return {
        textLength: allText.length,
        textPreview: allText.substring(0, 100),
        hasContent: allText.length > 100,
        chartElements: document.querySelectorAll('[class*="chart"], [class*="Chart"], svg').length,
        tableRows: document.querySelectorAll('table tbody tr').length,
        cardElements: document.querySelectorAll('[class*="card"], [class*="Card"]').length,
      };
    });

    console.log(`✅ ${pageInfo.name} (${pageInfo.url})`);
    console.log(`   Content: ${analysis.textLength} chars - ${analysis.hasContent ? '✓ HAS DATA' : '✗ EMPTY'}`);
    console.log(`   Charts: ${analysis.chartElements}, Tables: ${analysis.tableRows}, Cards: ${analysis.cardElements}`);
    console.log(`   Preview: "${analysis.textPreview}..."`);

  } catch (err) {
    console.log(`❌ ${pageInfo.name} (${pageInfo.url})`);
    console.log(`   Error: ${err.message}`);
  }
  console.log('');

  await page.close();
}

await browser.close();
console.log('=' .repeat(80) + '\n');
