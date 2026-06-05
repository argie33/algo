const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const errors = [];
  const logs = [];

  page.on('console', msg => {
    const text = msg.text();
    logs.push(`[${msg.type()}] ${text}`);
    if (msg.type() === 'error') {
      errors.push(text);
    }
  });

  page.on('pageerror', e => errors.push(`PAGE: ${e.message}`));
  page.on('response', resp => {
    if (resp.status() >= 400) {
      console.log(`❌ ${resp.status()} ${resp.url().split('localhost:5173/')[1]}`);
    }
  });

  try {
    await page.goto('http://localhost:5173/app/markets');
    await page.waitForTimeout(5000);
  } catch (e) {
    console.log(`Navigation error: ${e.message}`);
  }

  console.log('\n🔍 BROWSER DIAGNOSTICS\n');
  console.log('Logs (last 20):');
  logs.slice(-20).forEach(l => console.log(`  ${l}`));

  if (errors.length > 0) {
    console.log('\n❌ ERRORS:');
    errors.forEach(e => console.log(`  ${e}`));
  } else {
    console.log('\n✅ No errors logged');
  }

  // Check if root element exists and has content
  const rootContent = await page.evaluate(() => {
    const root = document.getElementById('root');
    return {
      exists: !!root,
      hasChildren: root ? root.children.length > 0 : false,
      innerHTML: root ? root.innerHTML.substring(0, 200) : ''
    };
  });

  console.log('\n📋 DOM STATE:');
  console.log(`  Root element exists: ${rootContent.exists}`);
  console.log(`  Root has children: ${rootContent.hasChildren}`);
  console.log(`  Root HTML preview: ${rootContent.innerHTML}`);

  await browser.close();
})();
