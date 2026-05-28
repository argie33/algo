const { chromium } = require('playwright');

(async () => {
  let browser;
  try {
    console.log('Starting browser...');
    browser = await chromium.launch({ headless: true });
    const context = await browser.createContext();
    const page = await context.newPage();

    // Wait for server to be ready
    console.log('Waiting for servers to start...');
    await new Promise(r => setTimeout(r, 3000));

    // Navigate to the trading signals page
    console.log('Navigating to trading signals page...');
    await page.goto('http://localhost:5173/app/signals', { waitUntil: 'networkidle', timeout: 15000 }).catch(e => {
      console.log('Navigation timeout (expected if servers not fully ready):', e.message);
    });

    // Wait for content to load
    await new Promise(r => setTimeout(r, 2000));

    // Get the page content
    const content = await page.content();

    // Check if key trading data fields are present in the page
    const hasTradeData = {
      'Buy zone': content.includes('Buy zone'),
      'Pivot': content.includes('Pivot'),
      'Initial stop': content.includes('Initial stop'),
      'Profit target': content.includes('Target T1') || content.includes('profit_target'),
      'Entry plan': content.includes('Entry plan'),
      'Buy/Sell Ratio': content.includes('BUY/SELL Ratio') || content.includes('Ratio'),
      'Tables present': content.includes('data-table') || content.includes('<table'),
    };

    console.log('\n✅ Trade Data Presence Check:');
    Object.entries(hasTradeData).forEach(([key, present]) => {
      console.log(`  ${present ? '✓' : '✗'} ${key}`);
    });

    // Try to find expanded row data
    const hasTableHeaders = content.includes('<th>') || content.includes('Symbol');
    console.log(`\n${hasTableHeaders ? '✓' : '✗'} Table headers present`);

    // Check for specific columns
    const columnChecks = {
      'Close': content.includes('Close'),
      'Buy Lvl': content.includes('Buy Lvl') || content.includes('buylevel'),
      'Stop': content.includes('Stop'),
      'SQS': content.includes('SQS'),
      'Base': content.includes('Base'),
      'Stage': content.includes('Stage'),
    };

    console.log('\n✅ Column Headers Check:');
    Object.entries(columnChecks).forEach(([key, present]) => {
      console.log(`  ${present ? '✓' : '✗'} ${key}`);
    });

    const allPresent = Object.values(hasTradeData).every(v => v);
    console.log(`\n${allPresent ? '✅ SUCCESS' : '❌ INCOMPLETE'}: All expected trade data fields are present`);

    await browser.close();
    process.exit(allPresent ? 0 : 1);
  } catch (error) {
    console.error('Error:', error.message);
    if (browser) await browser.close();
    process.exit(1);
  }
})();
