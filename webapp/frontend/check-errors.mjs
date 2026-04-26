import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const messages = [];
  page.on('console', msg => {
    messages.push({ type: msg.type(), text: msg.text() });
  });
  
  page.on('response', resp => {
    if (resp.status() >= 400) {
      messages.push({ type: 'http-error', text: `${resp.status()} ${resp.url()}` });
    }
  });
  
  await page.goto('http://localhost:5173/app/market');
  await page.waitForTimeout(3000);
  
  console.log('\n=== BROWSER CONSOLE MESSAGES ===\n');
  messages.forEach(m => {
    const icon = m.type === 'error' ? '❌' : m.type === 'warn' ? '⚠️' : '📝';
    console.log(`${icon} ${m.type}: ${m.text.substring(0, 150)}`);
  });
  
  // Check if root div has content
  const root = await page.$eval('#root', el => ({
    html: el.innerHTML.substring(0, 200),
    children: el.children.length,
    text: el.textContent.substring(0, 100)
  }));
  
  console.log('\nRoot element:');
  console.log(`  Children: ${root.children}`);
  console.log(`  Text: ${root.text || '(empty)'}`);
  console.log(`  HTML: ${root.html}`);

  await browser.close();
})();
