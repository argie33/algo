#!/usr/bin/env node
/**
 * Comprehensive Page Testing - Check all pages for:
 * 1. Console errors/warnings
 * 2. Missing data (displayed as "-" or "not available")
 * 3. Styling issues (black text on black, etc.)
 * 4. API 404 errors
 */

import puppeteer from 'puppeteer-core';

const BASE_URL = 'http://localhost:5173';
const PAGES = [
  { path: '/', name: 'Dashboard' },
  { path: '/stocks', name: 'Stocks' },
  { path: '/portfolios', name: 'Portfolios' },
  { path: '/signals', name: 'Trading Signals' },
  { path: '/scores', name: 'Stock Scores' },
  { path: '/economic', name: 'Economic Dashboard' },
  { path: '/sectors', name: 'Sectors' },
  { path: '/market', name: 'Market Health' },
  { path: '/research', name: 'Research' },
  { path: '/settings', name: 'Settings' },
];

const issues = {
  consoleErrors: [],
  missing404: [],
  missingData: [],
  styleIssues: [],
};

async function testPage(page, path, name) {
  console.log(`\n📄 Testing: ${name} (${path})`);
  const pageIssues = {
    errors: [],
    missing404: [],
    missingData: [],
  };

  // Collect console messages
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      pageIssues.errors.push(msg.text());
      console.log(`  ❌ Error: ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      console.log(`  ⚠️  Warning: ${msg.text()}`);
    }
  });

  // Collect failed requests (404s, etc.)
  page.on('response', (response) => {
    if (!response.ok() && response.url().includes('/api/')) {
      pageIssues.missing404.push(`${response.status()} ${response.url()}`);
      console.log(`  ❌ ${response.status()}: ${response.url()}`);
    }
  });

  try {
    const response = await page.goto(`${BASE_URL}${path}`, { waitUntil: 'networkidle2', timeout: 30000 });
    if (!response.ok()) {
      console.log(`  ❌ Page load failed: ${response.status()}`);
      pageIssues.errors.push(`Page load failed: ${response.status()}`);
      return pageIssues;
    }

    // Wait for content to load - longer timeout for slow API
    await new Promise(r => setTimeout(r, 4000));

    // Check for missing data patterns
    const missingDataElements = await page.evaluate(() => {
      const issues = [];
      // Look for dashes indicating missing data
      document.querySelectorAll('*').forEach((el) => {
        const text = el.textContent?.trim();
        if (text === '—' || text === '-' || text === '–') {
          const parent = el.closest('[class*="card"], [class*="table"], [class*="row"]')?.className || el.className;
          if (!issues.includes(parent)) {
            issues.push(parent);
          }
        }
      });
      return issues;
    });

    if (missingDataElements.length > 0) {
      pageIssues.missingData = missingDataElements;
      console.log(`  ⚠️  Missing data elements: ${missingDataElements.slice(0, 3).join(', ')}`);
    }

    // Check for styling issues
    const styleIssues = await page.evaluate(() => {
      const issues = [];
      document.querySelectorAll('*').forEach((el) => {
        const style = window.getComputedStyle(el);
        const textColor = style.color;
        const bgColor = style.backgroundColor;
        // Check for dark text on dark background
        if ((textColor.includes('rgb(0') || textColor.includes('rgb(255')) &&
            (bgColor.includes('rgb(0') || bgColor.includes('rgb(255'))) {
          issues.push({
            element: el.tagName,
            text: el.textContent?.substring(0, 30),
            textColor,
            bgColor,
          });
        }
      });
      return issues;
    });

    if (styleIssues.length > 0) {
      console.log(`  🎨 Potential styling issues: ${styleIssues.length}`);
    }

    console.log(`  ✅ Page loaded successfully`);
  } catch (error) {
    console.log(`  ❌ Error loading page: ${error.message}`);
    pageIssues.errors.push(error.message);
  }

  return pageIssues;
}

async function main() {
  console.log('🚀 Starting comprehensive page test...');
  console.log(`📍 Base URL: ${BASE_URL}`);
  console.log(`📋 Pages to test: ${PAGES.length}\n`);

  let browser;
  try {
    // Find Chrome executable
    const chromePath = await (async () => {
      const paths = [
        '/usr/bin/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
      ];
      for (const path of paths) {
        try {
          await import('fs').then(m => m.promises.access(path));
          return path;
        } catch {}
      }
      return null;
    })();

    if (!chromePath) {
      console.warn('⚠️  Chrome not found in standard locations, using puppeteer default');
    }

    browser = await puppeteer.launch({
      headless: 'new',
      executablePath: chromePath || undefined,
      args: ['--no-sandbox', '--disable-setuid-sandbox'],
    });

    const page = await browser.newPage();
    page.setDefaultNavigationTimeout(30000);
    page.setDefaultTimeout(30000);

    for (const pageInfo of PAGES) {
      const pageIssues = await testPage(page, pageInfo.path, pageInfo.name);
      issues.consoleErrors.push(...pageIssues.errors.map(e => `${pageInfo.name}: ${e}`));
      issues.missing404.push(...pageIssues.missing404.map(e => `${pageInfo.name}: ${e}`));
      issues.missingData.push(...pageIssues.missingData.map(e => `${pageInfo.name}: ${e}`));
    }

    await page.close();
  } catch (error) {
    console.error('Fatal error:', error);
    issues.consoleErrors.push(`Fatal error: ${error.message}`);
  } finally {
    if (browser) await browser.close();
  }

  // Print summary
  console.log('\n' + '='.repeat(70));
  console.log('📊 TEST SUMMARY');
  console.log('='.repeat(70));
  console.log(`\n❌ Console Errors: ${issues.consoleErrors.length}`);
  issues.consoleErrors.slice(0, 5).forEach(e => console.log(`   - ${e}`));
  if (issues.consoleErrors.length > 5) console.log(`   ... and ${issues.consoleErrors.length - 5} more`);

  console.log(`\n❌ API 404 Errors: ${issues.missing404.length}`);
  issues.missing404.slice(0, 5).forEach(e => console.log(`   - ${e}`));
  if (issues.missing404.length > 5) console.log(`   ... and ${issues.missing404.length - 5} more`);

  console.log(`\n⚠️  Missing Data Elements: ${issues.missingData.length}`);
  [...new Set(issues.missingData)].slice(0, 5).forEach(e => console.log(`   - ${e}`));

  process.exit(issues.consoleErrors.length > 0 || issues.missing404.length > 0 ? 1 : 0);
}

main();
