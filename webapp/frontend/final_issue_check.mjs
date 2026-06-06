import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

const issues = [];

const routes = [
  { path: '/app/markets', name: 'Markets (Public)', expectedContent: 'Market' },
  { path: '/app/economic', name: 'Economic (Public)', expectedContent: 'Economic' },
  { path: '/app/sectors', name: 'Sectors (Public)', expectedContent: 'Sector' },
  { path: '/app/deep-value', name: 'Deep Value (Public)', expectedContent: 'Value' },
  { path: '/app/sentiment', name: 'Sentiment (Public)', expectedContent: 'Sentiment' },
  { path: '/app/scores', name: 'Scores (Protected)', expectedContent: 'Score' },
  { path: '/app/trading-signals', name: 'Signals (Protected)', expectedContent: 'Signal' },
  { path: '/app/swing', name: 'Swing (Protected)', expectedContent: 'Swing' },
  { path: '/app/portfolio', name: 'Portfolio (Protected)', expectedContent: 'Portfolio' },
  { path: '/app/trades', name: 'Trades (Protected)', expectedContent: 'Trade' },
];

console.log('CHECKING ALL PAGES FOR ISSUES\n');

for (const route of routes) {
  try {
    await page.goto(`https://d2u93283nn45h2.cloudfront.net${route.path}`, {
      waitUntil: 'domcontentloaded',
      timeout: 10000
    }).catch(() => {});
    
    await page.waitForTimeout(1000);
    
    const result = await page.evaluate((expected) => {
      const text = document.body.innerText;
      const hasLoginForm = text.includes('Sign In') || text.includes('login');
      const hasExpectedContent = text.toLowerCase().includes(expected.toLowerCase());
      const isEmpty = text.length < 200;
      
      return {
        hasLoginForm,
        hasExpectedContent,
        isEmpty,
        textLength: text.length,
        visibleText: text.substring(0, 100),
      };
    }, route.expectedContent);
    
    let status = '✓';
    let issue = null;
    
    if (result.hasLoginForm) {
      status = '🔒';
      issue = 'Shows login page (auth required but not provided)';
    } else if (result.isEmpty) {
      status = '⚠️';
      issue = 'Page is empty or failed to render';
    } else if (!result.hasExpectedContent) {
      status = '❓';
      issue = `Page renders but missing expected content "${route.expectedContent}"`;
    }
    
    console.log(`${status} ${route.name.padEnd(30)} ${issue || 'Loads correctly'}`);
    
    if (issue) {
      issues.push({
        page: route.name,
        issue: issue,
        textLength: result.textLength,
      });
    }
  } catch (e) {
    console.log(`❌ ${route.name.padEnd(30)} Navigation failed: ${e.message}`);
    issues.push({
      page: route.name,
      issue: `Navigation error: ${e.message}`,
    });
  }
}

console.log(`\n\nSUMMARY: ${issues.length} issues found\n`);
issues.forEach(i => console.log(`- ${i.page}: ${i.issue}`));

await browser.close();
