/**
 * Multiple Test Runs - Catch intermittent violations
 */

import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';

async function multipleTestRuns() {
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

  const problematicPages = [
    { name: 'Technical Analysis', url: 'technical-analysis' },
    { name: 'Sentiment Analysis', url: 'sentiment-analysis' },
    { name: 'Earnings Calendar', url: 'earnings-calendar' }
  ];
  
  const allViolations = new Map();

  for (let run = 1; run <= 3; run++) {
    console.log(`\n🔄 TEST RUN ${run}/3`);
    console.log('='.repeat(50));
    
    for (const pageInfo of problematicPages) {
      try {
        await page.goto(`http://localhost:3000/${pageInfo.url}`);
        await page.waitForTimeout(8000); // Extended wait
        
        // Scroll to load any lazy content
        await page.evaluate(() => {
          window.scrollTo(0, document.body.scrollHeight);
        });
        await page.waitForTimeout(2000);
        await page.evaluate(() => {
          window.scrollTo(0, 0);
        });
        await page.waitForTimeout(1000);
        
        const accessibilityScanResults = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21aa'])
          .analyze();
        
        const violations = accessibilityScanResults.violations.filter(
          violation => violation.id === 'aria-input-field-name' || violation.id === 'aria-progressbar-name'
        );
        
        if (violations.length > 0) {
          violations.forEach(violation => {
            const key = `${pageInfo.name}-${violation.id}`;
            if (!allViolations.has(key)) {
              allViolations.set(key, []);
            }
            allViolations.get(key).push({
              run: run,
              violation: violation
            });
          });
          console.log(`❌ ${pageInfo.name}: ${violations.length} violations found in run ${run}`);
        } else {
          console.log(`✅ ${pageInfo.name}: No violations in run ${run}`);
        }
        
      } catch (error) {
        console.log(`❌ Error testing ${pageInfo.name} in run ${run}: ${error.message}`);
      }
    }
  }
  
  console.log('\n📊 SUMMARY OF ALL VIOLATIONS FOUND:');
  console.log('='.repeat(50));
  
  if (allViolations.size === 0) {
    console.log('✅ No violations found across all test runs!');
  } else {
    for (const [key, violationRuns] of allViolations) {
      const [pageName, violationType] = key.split('-');
      console.log(`\n❌ ${pageName.toUpperCase()}: ${violationType}`);
      console.log(`   Found in runs: ${violationRuns.map(v => v.run).join(', ')}`);
      
      // Show details from first occurrence
      const firstViolation = violationRuns[0].violation;
      firstViolation.nodes.forEach((node, index) => {
        console.log(`\n   Element ${index + 1}:`);
        console.log(`      Selector: ${node.target[0]}`);
        console.log(`      HTML: ${node.html.slice(0, 200)}${node.html.length > 200 ? '...' : ''}`);
        console.log(`      Issue: ${node.failureSummary}`);
      });
    }
  }
  
  await browser.close();
}

multipleTestRuns().catch(console.error);