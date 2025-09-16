#!/usr/bin/env node

const puppeteer = require('puppeteer');

async function debugAWSFrontend() {
  const browser = await puppeteer.launch({headless: true, args: ['--no-sandbox']});
  const page = await browser.newPage();

  const responses = [];
  page.on('response', response => {
    if (response.status() >= 400) {
      responses.push(`${response.url()} - ${response.status()}`);
    }
  });

  const errors = [];
  page.on('pageerror', error => {
    errors.push(`Page Error: ${error.message}`);
  });

  console.log('Loading AWS frontend...');
  await page.goto('https://d1copuy2oqlazx.cloudfront.net', {waitUntil: 'networkidle0', timeout: 20000});
  await new Promise(resolve => setTimeout(resolve, 3000));

  console.log('\nFailed Requests:');
  responses.forEach(resp => console.log(`  ❌ ${resp}`));

  console.log('\nPage Errors:');
  errors.forEach(error => console.log(`  ❌ ${error}`));

  const status = await page.evaluate(() => {
    const root = document.getElementById('root');
    return {
      hasReact: typeof window.React !== 'undefined',
      hasRoot: root && root.children.length > 0,
      rootHTML: root ? root.innerHTML.substring(0, 200) : 'NO ROOT',
      scripts: Array.from(document.scripts).map(s => s.src || 'inline').slice(-3),
      windowObject: Object.keys(window).filter(k => k.includes('React') || k.includes('__')).slice(0, 10)
    };
  });

  console.log('\nReact Status:');
  console.log(`  React loaded: ${status.hasReact}`);
  console.log(`  Root has content: ${status.hasRoot}`);
  console.log(`  Root HTML: ${status.rootHTML}`);
  console.log(`  Recent scripts: ${status.scripts.join(', ')}`);
  console.log(`  Window React objects: ${status.windowObject.join(', ')}`);

  await browser.close();
}

debugAWSFrontend().catch(console.error);