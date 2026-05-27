const { chromium } = require('playwright');
const axios = require('axios');
const http = require('http');

(async () => {
  console.log("COMPREHENSIVE DATA VERIFICATION");
  console.log("=" + "=".repeat(68));

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  const results = [];

  // Test each critical page
  const pages = [
    { name: 'Scores Dashboard', url: '/scores', checks: ['composite', 'score', 'ranking'] },
    { name: 'Portfolio', url: '/portfolio', checks: ['position', 'holding', 'value'] },
    { name: 'Trading Signals', url: '/signals', checks: ['signal', 'buy', 'sell'] },
    { name: 'Swing Candidates', url: '/swing-candidates', checks: ['candidate', 'trend', 'setup'] },
    { name: 'Markets Health', url: '/markets-health', checks: ['health', 'vix', 'breadth'] },
    { name: 'Sector Analysis', url: '/sectors', checks: ['sector', 'performance'] },
    { name: 'Economic Dashboard', url: '/economic', checks: ['economic', 'inflation', 'rate'] }
  ];

  for (const pageInfo of pages) {
    try {
      await page.goto(`http://localhost:5173${pageInfo.url}`, { waitUntil: 'networkidle', timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1500);

      const bodyText = await page.textContent('body');
      const lowerText = bodyText.toLowerCase();

      // Check for data presence
      let dataCount = 0;
      for (const check of pageInfo.checks) {
        if (lowerText.includes(check)) dataCount++;
      }

      const hasErrors = lowerText.includes('error') || lowerText.includes('failed');
      const hasData = dataCount > 0;

      results.push({
        name: pageInfo.name,
        url: pageInfo.url,
        dataPresent: hasData,
        hasErrors: hasErrors,
        keywords: dataCount
      });

      const status = hasData && !hasErrors ? "OK" : hasErrors ? "ERROR" : "WARN";
      console.log(`[${status}] ${pageInfo.name.padEnd(25)} (${dataCount}/${pageInfo.checks.length} checks)`);
    } catch (e) {
      console.log(`[FAIL] ${pageInfo.name.padEnd(25)} ${e.message.substring(0, 30)}`);
      results.push({ name: pageInfo.name, error: e.message });
    }
  }

  console.log("\n" + "=".repeat(70));
  console.log("SUMMARY:");
  const ok = results.filter(r => r.dataPresent && !r.hasErrors).length;
  const warn = results.filter(r => !r.dataPresent).length;
  console.log(`OK: ${ok}/${results.length}, Issues: ${warn}`);

  await browser.close();
})();
