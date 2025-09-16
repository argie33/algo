#!/usr/bin/env node

const puppeteer = require('puppeteer');

async function debugJSErrors() {
  const browser = await puppeteer.launch({headless: true, args: ['--no-sandbox']});
  const page = await browser.newPage();

  const allMessages = [];
  const errors = [];

  page.on('console', msg => {
    allMessages.push(`${msg.type()}: ${msg.text()}`);
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('pageerror', error => {
    errors.push(`Page Error: ${error.message}`);
    allMessages.push(`Page Error: ${error.message}`);
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      allMessages.push(`HTTP Error: ${response.url()} - ${response.status()}`);
    }
  });

  console.log('Loading AWS frontend with detailed error tracking...');
  await page.goto('https://d1copuy2oqlazx.cloudfront.net', {waitUntil: 'networkidle0', timeout: 20000});

  // Wait for scripts to potentially load and execute
  await new Promise(resolve => setTimeout(resolve, 5000));

  console.log('\n=== ALL CONSOLE MESSAGES ===');
  allMessages.forEach(msg => console.log(msg));

  console.log('\n=== ERROR SUMMARY ===');
  console.log(`Total errors: ${errors.length}`);
  errors.forEach(error => console.log(`❌ ${error}`));

  const finalState = await page.evaluate(() => {
    return {
      hasReact: typeof window.React !== 'undefined',
      hasReactDOM: typeof window.ReactDOM !== 'undefined',
      rootContent: document.getElementById('root').innerHTML,
      windowKeys: Object.keys(window).filter(k => k.includes('React') || k.includes('__') || k.startsWith('_')).slice(0, 15),
      scriptsLoaded: document.scripts.length,
      configLoaded: typeof window.__CONFIG__ !== 'undefined'
    };
  });

  console.log('\n=== FINAL STATE ===');
  console.log('React available:', finalState.hasReact);
  console.log('ReactDOM available:', finalState.hasReactDOM);
  console.log('Root content length:', finalState.rootContent.length);
  console.log('Scripts loaded:', finalState.scriptsLoaded);
  console.log('Config loaded:', finalState.configLoaded);
  console.log('Window keys:', finalState.windowKeys.join(', '));

  await browser.close();
}

debugJSErrors().catch(console.error);