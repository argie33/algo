#!/usr/bin/env node
import puppeteer from 'puppeteer-core';

const BASE_URL = 'http://localhost:5173';
const chromePath = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';

async function diagnose() {
  console.log('DIAGNOSTIC REPORT - Page Content Analysis');
  console.log('='.repeat(80));

  let browser;
  try {
    browser = await puppeteer.launch({
      executablePath: chromePath,
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    });

    const testPages = [
      { path: '/app/scores', name: 'Scores' },
      { path: '/app/markets', name: 'Markets' },
      { path: '/app/trading-signals', name: 'Trading Signals' },
    ];

    for (const p of testPages) {
      const url = `${BASE_URL}${p.path}`;
      const page = await browser.newPage();

      console.log(`\n📄 PAGE: ${p.name} (${p.path})`);
      console.log('-'.repeat(80));

      try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
        await new Promise(r => setTimeout(r, 3000));

        const content = await page.evaluate(() => {
          return {
            title: document.title,
            url: document.location.pathname,
            errors: Array.from(document.querySelectorAll('[class*="error"], [class*="Error"]'))
              .map(el => el.innerText)
              .filter(Boolean)
              .slice(0, 5),
            allText: document.body.innerText.substring(0, 1000),
            tableCount: document.querySelectorAll('table').length,
            tableRows: document.querySelectorAll('table tbody tr').length,
            divCount: document.querySelectorAll('div[role="region"]').length,
            apiErrors: document.body.innerText.match(/error|failed|unable|500|401|403|404/gi) || [],
          };
        });

        console.log(`Title: ${content.title}`);
        console.log(`URL: ${content.url}`);
        console.log(`Tables: ${content.tableCount} (rows: ${content.tableRows})`);
        console.log(`Data Regions: ${content.divCount}`);

        if (content.errors.length > 0) {
          console.log(`\n⚠️  Error Elements Found:`);
          content.errors.forEach(e => console.log(`   - ${e.substring(0, 100)}`));
        }

        if (content.apiErrors.length > 0) {
          console.log(`\n⚠️  API/Network Errors Detected:`);
          console.log(`   ${Array.from(new Set(content.apiErrors)).join(', ')}`);
        }

        console.log(`\n📝 Page Content (first 500 chars):`);
        console.log(content.allText.substring(0, 500));

      } catch (error) {
        console.log(`❌ Load failed: ${error.message}`);
      }

      await page.close();
    }

  } catch (error) {
    console.error('Fatal error:', error.message);
  } finally {
    if (browser) await browser.disconnect();
  }
}

diagnose();
