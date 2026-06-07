#!/usr/bin/env node

import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });

const pages = [
  { url: '/app/markets', name: 'Market Health' },
  { url: '/app/sectors', name: 'Sector Analysis' },
  { url: '/app/swing', name: 'Swing Candidates' },
  { url: '/app/scores', name: 'Stock Scores' },
  { url: '/app/portfolio', name: 'Portfolio' }
];

console.log('🔍 FINAL COMPREHENSIVE PAGE TEST\n');
console.log('=' .repeat(80) + '\n');

const results = [];

for (const pageInfo of pages) {
  const page = await browser.newPage();

  try {
    await page.goto('http://localhost:5173' + pageInfo.url, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1500);

    const state = await page.evaluate(() => {
      const main = document.querySelector('main');
      const text = (main?.innerText || '').trim();
      return {
        textLength: text.length,
        hasContent: text.length > 100,
        preview: text.substring(0, 80),
      };
    });

    const icon = state.hasContent ? '✅' : '⚠️ ';
    const status = state.hasContent ? 'WORKING' : 'LOADING';
    results.push({
      name: pageInfo.name,
      working: state.hasContent,
      chars: state.textLength
    });

    console.log(`${icon} ${pageInfo.name.padEnd(20)} | ${state.textLength.toString().padEnd(6)} chars | ${status}`);

  } catch (err) {
    console.log(`❌ ${pageInfo.name.padEnd(20)} | ERROR: ${err.message.substring(0, 40)}`);
    results.push({
      name: pageInfo.name,
      working: false,
      error: err.message
    });
  }

  await page.close();
}

console.log('\n' + '=' .repeat(80) + '\n');
console.log('SUMMARY:');
const working = results.filter(r => r.working).length;
const total = results.length;
console.log(`  Working: ${working}/${total}`);

if (working === total) {
  console.log('\n✅ ALL PAGES WORKING!');
} else {
  console.log('\n❌ Some pages still need fixing:');
  results.filter(r => !r.working).forEach(r => {
    console.log(`  - ${r.name}: ${r.error || 'No content'}`);
  });
}

console.log('');

await browser.close();
