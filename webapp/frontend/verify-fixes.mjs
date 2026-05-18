import { chromium } from '@playwright/test';

const pages = [
  { path: '/app/market', name: 'Market Overview' },
  { path: '/app/sectors', name: 'Sector Analysis' },
  { path: '/app/scores', name: 'Stock Scores' },
  { path: '/app/sentiment', name: 'Sentiment' },
  { path: '/app/economic', name: 'Economic Dashboard' },
  { path: '/app/trading-signals', name: 'Trading Signals' },
  { path: '/app/portfolio', name: 'Portfolio Dashboard' },
  { path: '/app/settings', name: 'Settings' },
];

(async () => {
  try {
    const browser = await chromium.launch();
    const results = [];

    for (const page of pages) {
      const context = await browser.newContext();
      const p = await context.newPage();
      const messages = [];

      p.on('console', msg => {
        messages.push({ type: msg.type(), text: msg.text() });
      });

      try {
        await p.goto(`http://localhost:5173${page.path}`, { waitUntil: 'networkidle', timeout: 15000 });
        await p.waitForTimeout(1500);
      } catch (e) {
        messages.push({ type: 'error', text: `Load failed: ${e.message}` });
      }

      const errors = messages.filter(m => m.type === 'error');
      const warnings = messages.filter(m => m.type === 'warning');

      results.push({
        name: page.name,
        errors: errors.length,
        warnings: warnings.length,
        errorList: errors.map(e => e.text.substring(0, 80)),
        warningList: warnings.map(w => w.text.substring(0, 80))
      });

      await context.close();
    }

    await browser.close();

    console.log('\n✅ AUDIT RESULTS\n');
    let totalErrors = 0, totalWarnings = 0, pagesWithIssues = 0;

    results.forEach(r => {
      totalErrors += r.errors;
      totalWarnings += r.warnings;
      if (r.errors > 0 || r.warnings > 0) {
        pagesWithIssues++;
        console.log(`❌ ${r.name}: ${r.errors} errors, ${r.warnings} warnings`);
        if (r.errorList.length > 0) console.log(`   Errors: ${r.errorList.join(' | ')}`);
        if (r.warningList.length > 0) console.log(`   Warnings: ${r.warningList.join(' | ')}`);
      } else {
        console.log(`✅ ${r.name}`);
      }
    });

    console.log(`\n📊 SUMMARY: ${results.length} pages, ${pagesWithIssues} with issues`);
    console.log(`Total errors: ${totalErrors}, Total warnings: ${totalWarnings}`);
    console.log(`Status: ${totalErrors === 0 && totalWarnings === 0 ? '✅ ALL CLEAN' : '⚠️ ISSUES REMAIN'}\n`);

    process.exit(totalErrors > 0 ? 1 : 0);
  } catch (err) {
    console.error('Audit failed:', err.message);
    process.exit(1);
  }
})();
