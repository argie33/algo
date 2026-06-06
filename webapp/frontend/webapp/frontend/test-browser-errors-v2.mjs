import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const errors = [];
const warnings = [];
const logs = [];

page.on('console', (msg) => {
  const entry = { type: msg.type(), text: msg.text() };
  if (msg.type() === 'error') errors.push(entry);
  else if (msg.type() === 'warn') warnings.push(entry);
  else logs.push(entry);
});

page.on('pageerror', (error) => {
  errors.push({ type: 'pageerror', text: error.message + '\n' + error.stack });
});

console.log('Loading http://localhost:5173...');
await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });

// Wait for any async errors
await page.waitForTimeout(3000);

console.log('\n=== CONSOLE ERRORS ===');
if (errors.length === 0) {
  console.log('✓ No errors');
} else {
  errors.forEach((e, i) => {
    console.log(`\n${i+1}. [${e.type}]`);
    console.log(e.text.substring(0, 300));
  });
}

console.log('\n=== CONSOLE WARNINGS ===');
const uniqueWarnings = [...new Set(warnings.map(w => w.text))];
if (uniqueWarnings.length === 0) {
  console.log('✓ No warnings');
} else {
  uniqueWarnings.forEach((w, i) => {
    console.log(`${i+1}. ${w.substring(0, 200)}`);
  });
}

// Screenshot
await page.screenshot({ path: 'test-screenshot.png' });
console.log('\n✓ Screenshot saved');

// Check if page is interactive
const hasRoot = await page.evaluate(() => !!document.querySelector('#root > div'));
console.log(`Page root rendered: ${hasRoot}`);

await browser.close();
