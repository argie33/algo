import { test } from "@playwright/test";

test('debug market overview elements', async ({ page }) => {
  // Monitor console messages
  const consoleMessages = [];
  page.on('console', (msg) => {
    consoleMessages.push(`${msg.type()}: ${msg.text()}`);
  });

  console.log('📍 Navigating to /market...');
  await page.goto('/market', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  console.log('🔍 Console messages:', consoleMessages.slice(-10)); // Last 10 messages

  const elements = await page.evaluate(() => {
    return {
      cards: document.querySelectorAll('.MuiCard-root').length,
      tables: document.querySelectorAll('table').length,
      testidMarket: document.querySelectorAll('[data-testid*="market"]').length,
      classMarket: document.querySelectorAll('[class*="market"]').length,
      classOverview: document.querySelectorAll('[class*="overview"]').length,
      hasContent: document.body.innerHTML.length > 1000,
      bodyLength: document.body.innerHTML.length,
      title: document.title,
      url: window.location.href,
      rootExists: !!document.getElementById('root'),
      rootContent: document.getElementById('root')?.children.length || 0
    };
  });

  console.log('🔍 Elements found:', elements);

  // Check for any error messages
  const errorText = await page.evaluate(() => {
    const errors = Array.from(document.querySelectorAll('*')).filter(el =>
      el.textContent && (
        el.textContent.includes('Error') ||
        el.textContent.includes('error') ||
        el.textContent.includes('Loading') ||
        el.textContent.includes('loading')
      )
    );
    return errors.map(el => el.textContent.slice(0, 100));
  });

  console.log('⚠️ Error/Loading messages:', errorText);

  // Try to get page source
  const content = await page.content();
  console.log('📄 Page source length:', content.length);
  console.log('📄 Contains MuiCard:', content.includes('MuiCard'));
  console.log('📄 Contains market-overview-page:', content.includes('market-overview-page'));
  console.log('📄 Contains MarketOverview:', content.includes('MarketOverview'));
  console.log('📄 Contains TabPanel:', content.includes('TabPanel'));
  console.log('📄 Contains data-testid:', content.includes('data-testid'));

  // Check what's actually in the root
  const rootHTML = await page.evaluate(() => {
    const root = document.getElementById('root');
    return root ? root.innerHTML.slice(0, 500) : 'No root found';
  });
  console.log('📄 Root content (first 500 chars):', rootHTML);
});