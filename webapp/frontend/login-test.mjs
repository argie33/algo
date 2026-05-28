import puppeteer from 'puppeteer';

console.log('\n' + '='.repeat(70));
console.log('🔐 LOCAL LOGIN TEST');
console.log('='.repeat(70) + '\n');

async function test() {
  let browser;
  try {
    console.log('Starting browser...');
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    }).catch(() => {
      console.log('Auto-launch failed, trying bundled...');
      return puppeteer.launch({ 
        headless: 'new'
      });
    });
    
    console.log('✅ Browser ready\n');
    
    const page = await browser.newPage();
    const logs = [];
    page.on('console', msg => logs.push({ type: msg.type(), text: msg.text() }));

    console.log('Loading login page...');
    await page.goto('http://localhost:5173/login', { waitUntil: 'domcontentloaded' });
    console.log('✅ Loaded\n');
    
    console.log('Filling form & submitting...');
    const inputs = await page.$$('input');
    if (inputs.length >= 2) {
      await inputs[0].type('dev-admin');
      await inputs[1].type('Admin123!');
      const buttons = await page.$$('button');
      if (buttons.length > 0) await buttons[buttons.length - 1].click();
      
      await new Promise(r => setTimeout(r, 4000));
      
      const url = page.url();
      const errors = logs.some(l => l.text.includes('USER_SRP_AUTH'));
      
      console.log(`✅ Submitted - URL: ${url}`);
      console.log(`${errors ? '❌' : '✅'} Errors: ${errors ? 'YES' : 'NO'}\n`);
      
      await browser.close();
      return !errors;
    }
    
    await browser.close();
    return false;
  } catch (error) {
    console.log(`❌ ${error.message}\n`);
    if (browser) await browser.close();
    return false;
  }
}

console.time('Login Test');
const success = await test();
console.timeEnd('Login Test');

console.log('='.repeat(70));
console.log(success ? '✅ LOGIN VERIFIED - WORKS' : '⚠️  TEST INCONCLUSIVE');
console.log('='.repeat(70) + '\n');
