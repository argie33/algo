#!/usr/bin/env node
/**
 * Verify pages have real content after routing fix
 */

import puppeteer from 'puppeteer';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const pages = [
  { path: '/', name: 'Home' },
  { path: '/stocks', name: 'Stocks' },
  { path: '/economic', name: 'Economic' },
  { path: '/signals', name: 'Signals' },
  { path: '/sectors', name: 'Sectors' },
];

async function checkPage(path, name) {
  let browser = null;
  let page = null;

  try {
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    page = await browser.newPage();
    const response = await page.goto(`${FRONTEND_URL}${path}`, {
      waitUntil: 'networkidle2',
      timeout: 15000
    });

    await new Promise(r => setTimeout(r, 2000));

    const content = await page.evaluate(() => ({
      textLength: document.body.innerText.length,
      hasHeadings: document.querySelectorAll('h1, h2, h3, h4, h5, h6').length > 0,
      headingCount: document.querySelectorAll('h1, h2, h3, h4, h5, h6').length,
      hasData: document.body.innerText.length > 200,
      elementCount: document.querySelectorAll('*').length,
    }));

    const status = response.status();
    const isGood = status === 200 && content.hasData;

    return {
      path,
      name,
      status,
      ...content,
      ok: isGood
    };

  } catch (error) {
    return {
      path,
      name,
      error: error.message,
      ok: false
    };
  } finally {
    if (page) await page.close();
    if (browser) await browser.close();
  }
}

async function main() {
  console.log('\n' + '='.repeat(70));
  console.log('PAGE CONTENT VERIFICATION AFTER ROUTING FIX');
  console.log('='.repeat(70) + '\n');

  let allGood = true;

  for (const p of pages) {
    const result = await checkPage(p.path, p.name);

    if (result.error) {
      console.log(`✗ ${result.name} (${result.path}): Error - ${result.error}`);
      allGood = false;
    } else {
      const status = result.ok ? '✓' : '✗';
      console.log(`${status} ${result.name} (${result.path})`);
      console.log(`   HTTP ${result.status} | ${result.textLength} chars | ${result.headingCount} headings | ${result.elementCount} elements`);
      if (!result.ok) {
        allGood = false;
      }
    }
  }

  console.log('\n' + '='.repeat(70));
  if (allGood) {
    console.log('✅ ALL PAGES HAVE CONTENT');
  } else {
    console.log('❌ SOME PAGES ARE MISSING CONTENT');
  }
  console.log('='.repeat(70) + '\n');

  process.exit(allGood ? 0 : 1);
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
