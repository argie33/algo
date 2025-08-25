/**
 * Comprehensive Application Accessibility Test
 * Tests ALL application pages for WCAG 2.1 AA compliance
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

const pages = [
  { name: 'Dashboard', url: '' },
  { name: 'Real-Time Data', url: 'realtime' },
  { name: 'Portfolio', url: 'portfolio' },
  { name: 'Market Overview', url: 'market-overview' },
  { name: 'Settings', url: 'settings' },
  { name: 'Stock Explorer', url: 'stocks' },
  { name: 'Technical Analysis', url: 'technical' },
  { name: 'Sentiment Analysis', url: 'sentiment' },
  { name: 'Trading Signals', url: 'trading' },
  { name: 'Watchlist', url: 'watchlist' },
  { name: 'Earnings Calendar', url: 'earnings' },
  { name: 'Backtest', url: 'backtest' },
  { name: 'Advanced Screener', url: 'screener-advanced' },
  { name: 'Financial Data', url: 'financial-data' },
  { name: 'Service Health', url: 'service-health' },
  { name: 'Scores Dashboard', url: 'scores' }
];

async function testAllPages() {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Setup authentication and API mocking
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

  console.log(`\n🔍 COMPREHENSIVE APPLICATION ACCESSIBILITY ANALYSIS:`);
  console.log('='.repeat(80));
  
  let totalViolations = 0;
  let pagesWithIssues = 0;
  let perfectPages = 0;
  const violationSummary = {};

  for (const pageInfo of pages) {
    console.log(`\n📄 Testing: ${pageInfo.name}`);
    console.log('-'.repeat(50));
    
    try {
      const url = pageInfo.url ? 
        `http://localhost:3001/${pageInfo.url}` : 
        'http://localhost:3001/';
      
      await page.goto(url);
      await page.waitForTimeout(3000); // Allow page to load
      
      // Run accessibility scan
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
        .analyze();
      
      const violations = results.violations;
      totalViolations += violations.length;
      
      if (violations.length === 0) {
        console.log(`✅ PERFECT: No accessibility violations found!`);
        perfectPages++;
      } else {
        console.log(`❌ ISSUES: ${violations.length} accessibility violations found`);
        pagesWithIssues++;
        
        violations.forEach((violation, index) => {
          console.log(`   ${index + 1}. ${violation.id}: ${violation.description}`);
          console.log(`      Impact: ${violation.impact} | Elements: ${violation.nodes.length}`);
          
          // Track violation types
          if (violationSummary[violation.id]) {
            violationSummary[violation.id].count++;
            violationSummary[violation.id].pages.push(pageInfo.name);
          } else {
            violationSummary[violation.id] = {
              count: 1,
              pages: [pageInfo.name],
              description: violation.description,
              impact: violation.impact
            };
          }
        });
      }
      
    } catch (error) {
      console.log(`❌ ERROR testing ${pageInfo.name}: ${error.message}`);
    }
  }
  
  // Summary Report
  console.log(`\n📊 COMPREHENSIVE ACCESSIBILITY SUMMARY:`);
  console.log('='.repeat(80));
  console.log(`✅ Perfect pages: ${perfectPages}/${pages.length}`);
  console.log(`❌ Pages with issues: ${pagesWithIssues}/${pages.length}`);
  console.log(`🔢 Total violations: ${totalViolations}`);
  
  if (Object.keys(violationSummary).length > 0) {
    console.log(`\n🎯 VIOLATION BREAKDOWN BY TYPE:`);
    Object.entries(violationSummary).forEach(([violationType, data]) => {
      console.log(`\n❌ ${violationType}:`);
      console.log(`   Description: ${data.description}`);
      console.log(`   Impact: ${data.impact}`);
      console.log(`   Occurrences: ${data.count}`);
      console.log(`   Pages affected: ${data.pages.join(', ')}`);
    });
  }
  
  console.log(`\n🎯 NEXT ACTIONS:`);
  if (perfectPages === pages.length) {
    console.log(`🎉 ALL PAGES PERFECT! Complete WCAG 2.1 AA compliance achieved!`);
  } else {
    console.log(`🔧 Focus on fixing: ${Object.keys(violationSummary).join(', ')}`);
    console.log(`📄 Priority pages: ${violationSummary && Object.values(violationSummary).length > 0 ? 
      [...new Set(Object.values(violationSummary).flatMap(v => v.pages))].slice(0, 5).join(', ') : 'None'}`);
  }
  
  await browser.close();
  console.log('\n✅ Comprehensive accessibility analysis complete!');
}

testAllPages().catch(console.error);