import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

// Capture API errors in detail
const apiErrors = [];
page.on('response', res => {
  if (res.url().includes('/api/')) {
    res.json().then(data => {
      if (res.status() >= 400) {
        apiErrors.push({
          url: res.url(),
          status: res.status(),
          body: JSON.stringify(data).substring(0, 200),
        });
      }
    }).catch(() => {});
  }
});

console.log('Loading /app/scores...');
await page.goto('https://d2u93283nn45h2.cloudfront.net/app/scores', {
  waitUntil: 'domcontentloaded',
  timeout: 15000
}).catch(e => console.log('Nav error:', e.message));

await page.waitForTimeout(3000);

const pageContent = await page.evaluate(() => {
  // Get all visible text
  const bodyText = document.body.innerText;
  
  // Check for auth requirements
  const hasAuthError = bodyText.includes('Unauthorized') || bodyText.includes('login') || bodyText.includes('authenticate');
  
  // Check for loading state
  const hasLoading = bodyText.includes('Loading');
  
  // Check for errors
  const hasError = bodyText.includes('Error') || bodyText.includes('error');
  
  // Get root content
  const root = document.getElementById('root');
  const rootHTML = root?.innerHTML || '';
  
  // Check for empty content
  const isEmpty = rootHTML.length < 500;
  
  return {
    isEmpty,
    hasAuthError,
    hasLoading,
    hasError,
    bodyTextLength: bodyText.length,
    firstText: bodyText.substring(0, 300),
    rootLength: rootHTML.length,
  };
});

console.log('\n=== PAGE STATE ===');
console.log(JSON.stringify(pageContent, null, 2));

console.log('\n=== API ERRORS ===');
apiErrors.forEach(err => console.log(`${err.status} ${err.url}: ${err.body}`));

// Take screenshot
await page.screenshot({ path: '/tmp/scores_page.png' });
console.log('\nScreenshot: /tmp/scores_page.png');

await browser.close();
