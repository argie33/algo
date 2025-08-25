/**
 * Violation Capture - Run comprehensive test with immediate violation capture and fixes
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function captureAndAnalyzeViolations() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  await page.addInitScript(() => {
    localStorage.setItem('financial_auth_token', 'a11y-test-token');
    localStorage.setItem('api_keys_status', JSON.stringify({
      alpaca: { configured: true, valid: true },
      polygon: { configured: true, valid: true },
      finnhub: { configured: true, valid: true }
    }));
  });
  
  await page.route('**/api/**', route => {
    route.fulfill({ json: { success: true, data: {} } });
  });

  const allPages = [
    { name: 'Dashboard', url: 'dashboard' },
    { name: 'Real-Time Data', url: 'realtime' },
    { name: 'Portfolio', url: 'portfolio' },
    { name: 'Market Overview', url: 'market-overview' },
    { name: 'Settings', url: 'settings' },
    { name: 'Stock Explorer', url: 'stock-explorer' },
    { name: 'Technical Analysis', url: 'technical-analysis' },
    { name: 'Sentiment Analysis', url: 'sentiment-analysis' },
    { name: 'Trading Signals', url: 'trading-signals' },
    { name: 'Watchlist', url: 'watchlist' },
    { name: 'Earnings Calendar', url: 'earnings-calendar' },
    { name: 'Backtest', url: 'backtest' },
    { name: 'Advanced Screener', url: 'screener' },
    { name: 'Financial Data', url: 'financial-data' },
    { name: 'Service Health', url: 'service-health' },
    { name: 'Scores Dashboard', url: 'scores' }
  ];

  let perfectPages = 0;
  let pagesWithIssues = 0;
  let totalViolations = 0;
  let foundViolations = [];

  console.log('🔍 COMPREHENSIVE VIOLATION CAPTURE:');
  console.log('='.repeat(80));

  for (const pageInfo of allPages) {
    try {
      await page.goto(`http://localhost:3000/${pageInfo.url}`);
      await page.waitForTimeout(4000);

      const accessibilityScanResults = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();

      if (accessibilityScanResults.violations.length === 0) {
        console.log(`✅ ${pageInfo.name}: PERFECT`);
        perfectPages++;
      } else {
        console.log(`❌ ${pageInfo.name}: ${accessibilityScanResults.violations.length} violations`);
        pagesWithIssues++;
        totalViolations += accessibilityScanResults.violations.length;
        
        // Capture violation details immediately
        for (const violation of accessibilityScanResults.violations) {
          console.log(`\n   🚨 ${violation.id}: ${violation.description}`);
          console.log(`      Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
          
          foundViolations.push({
            page: pageInfo.name,
            url: pageInfo.url,
            violationType: violation.id,
            description: violation.description,
            impact: violation.impact,
            elementCount: violation.nodes.length,
            elements: violation.nodes.map(node => ({
              selector: node.target[0],
              html: node.html.slice(0, 200),
              issue: node.failureSummary
            }))
          });
          
          // Show first few elements for immediate analysis
          violation.nodes.slice(0, 2).forEach((node, index) => {
            console.log(`\n      Element ${index + 1}:`);
            console.log(`         Selector: ${node.target[0]}`);
            console.log(`         HTML: ${node.html.slice(0, 150)}...`);
            console.log(`         Issue: ${node.failureSummary}`);
          });
        }
      }
      
    } catch (error) {
      console.log(`❌ Error testing ${pageInfo.name}: ${error.message}`);
    }
  }

  console.log('\n📊 FINAL RESULTS:');
  console.log('='.repeat(80));
  console.log(`✅ Perfect pages: ${perfectPages}/16`);
  console.log(`❌ Pages with issues: ${pagesWithIssues}/16`);
  console.log(`🔢 Total violations: ${totalViolations}`);

  if (foundViolations.length > 0) {
    console.log('\n🎯 DETAILED VIOLATION BREAKDOWN:');
    console.log('='.repeat(80));
    
    // Group violations by type
    const violationsByType = {};
    foundViolations.forEach(v => {
      if (!violationsByType[v.violationType]) {
        violationsByType[v.violationType] = [];
      }
      violationsByType[v.violationType].push(v);
    });
    
    for (const [type, violations] of Object.entries(violationsByType)) {
      console.log(`\n❌ ${type.toUpperCase()}:`);
      console.log(`   Occurrences: ${violations.length}`);
      console.log(`   Pages affected: ${violations.map(v => v.page).join(', ')}`);
      
      // Show specific fix recommendations
      violations.forEach(violation => {
        console.log(`\n   📄 ${violation.page}:`);
        violation.elements.forEach((element, index) => {
          console.log(`      ${index + 1}. ${element.selector}`);
          console.log(`         HTML: ${element.html}...`);
          console.log(`         Issue: ${element.issue}`);
          
          // Provide specific fix guidance
          if (type === 'aria-input-field-name') {
            console.log(`         🔧 FIX: Add aria-label="descriptive text" or aria-labelledby="label-id"`);
          } else if (type === 'aria-progressbar-name') {
            console.log(`         🔧 FIX: Add aria-label="progress description" to progress elements`);
          }
        });
      });
    }
  }

  await browser.close();
  console.log('\n✅ Violation capture complete!');
}

captureAndAnalyzeViolations().catch(console.error);