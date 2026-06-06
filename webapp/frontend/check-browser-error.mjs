import puppeteer from 'puppeteer-core';
import path from 'path';

// Find Chrome on Windows
const chromePaths = [
  'C:\Program Files\Google\Chrome\Application\chrome.exe',
  'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
  process.env.CHROME_PATH,
];

let chromePath = null;
for (const p of chromePaths) {
  if (p) {
    try {
      const fs = await import('fs');
      if (fs.existsSync(p)) {
        chromePath = p;
        break;
      }
    } catch (e) {
      // ignore
    }
  }
}

if (!chromePath) {
  console.log('Chrome not found, trying puppeteer default...');
  const puppeteerChrome = puppeteer.executablePath();
  chromePath = puppeteerChrome;
  console.log('Using:', chromePath);
}

const browser = await puppeteer.launch({
  executablePath: chromePath,
  headless: 'new',
  args: ['--no-sandbox', '--disable-setuid-sandbox'],
});

const page = await browser.newPage();

// Capture all console messages
const consoleLogs = [];
page.on('console', (msg) => {
  consoleLogs.push({
    type: msg.type(),
    text: msg.text(),
    location: msg.location(),
  });
});

// Capture page errors
const errors = [];
page.on('pageerror', (err) => {
  errors.push({
    message: err.message,
    stack: err.stack,
  });
});

console.log('Navigating to http://localhost:5176...');
try {
  await page.goto('http://localhost:5176', { waitUntil: 'networkidle2', timeout: 15000 });
  console.log('Page loaded');
} catch (e) {
  console.error('Navigation error:', e.message);
}

// Wait for any async JS errors
await page.waitForTimeout(3000);

console.log('\n=== CONSOLE LOGS ===');
consoleLogs.forEach((log) => {
  console.log(`[${log.type}] ${log.text}`);
});

console.log('\n=== PAGE ERRORS ===');
errors.forEach((err) => {
  console.log(`ERROR: ${err.message}`);
  if (err.stack) console.log(err.stack.substring(0, 300));
});

// Get the current URL
const url = page.url();
console.log(`\nCurrent URL: ${url}`);

// Take screenshot
await page.screenshot({ path: 'browser-screenshot.png', fullPage: false });
console.log('Screenshot saved');

await browser.close();
