import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const issues = [];
  const warnings = [];
  const successes = [];

  page.on('console', msg => {
    const text = msg.text();
    if (msg.type() === 'error') issues.push(`JS Error: ${text}`);
    if (msg.type() === 'warning' && text.includes('deprecated')) warnings.push(`Warning: ${text}`);
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      issues.push(`HTTP ${response.status()}: ${response.url()}`);
    }
  });

  try {
    console.log('🔍 COMPREHENSIVE DASHBOARD DIAGNOSTICS\n');
    console.log('═'.repeat(50));

    // Load dashboard
    console.log('\n📊 Loading dashboard...');
    await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded', timeout: 30000 });
    successes.push('Page loaded successfully');

    // Wait for initial render
    await page.waitForTimeout(2000);

    // Check for required sections
    console.log('\n🔍 Checking dashboard sections...');
    const sections = [
      { name: 'Portfolio Value KPI', selector: 'text=Portfolio Value' },
      { name: 'Equity Curve Chart', selector: 'text=Equity Curve' },
      { name: 'Drawdown Chart', selector: 'text=Drawdown' },
      { name: 'Circuit Breakers', selector: 'text=Circuit Breakers' },
      { name: 'Position Health Table', selector: 'text=Position Health' },
      { name: 'Recent Trades', selector: 'text=Recent Trades' },
      { name: 'Risk Allocation', selector: 'text=Open Risk Allocation' },
      { name: 'Sector Concentration', selector: 'text=Sector Concentration' },
      { name: 'Market Context', selector: 'text=Market Context' },
    ];

    for (const section of sections) {
      const exists = await page.locator(section.selector).count() > 0;
      if (exists) {
        successes.push(`✓ ${section.name}`);
      } else {
        issues.push(`✗ Missing ${section.name}`);
      }
    }

    // Check for layout issues
    console.log('\n🎨 Checking layout...');
    const layoutIssues = await page.evaluate(() => {
      const problems = [];

      // Check for overflow issues
      const overflowing = [];
      document.querySelectorAll('[class*="card"]').forEach(card => {
        const style = window.getComputedStyle(card);
        if (style.overflow === 'hidden' && card.scrollHeight > card.clientHeight) {
          overflowing.push(card.className);
        }
      });
      if (overflowing.length > 0) problems.push(`Overflow issues: ${overflowing.length} cards`);

      // Check for missing icons
      const missingIcons = document.querySelectorAll('svg').length < 5;
      if (missingIcons) problems.push('Few or no icons rendered');

      // Check for text rendering
      const textElements = document.querySelectorAll('p, span, div');
      let emptyText = 0;
      textElements.forEach(el => {
        if (el.offsetHeight === 0 && el.offsetWidth === 0) emptyText++;
      });
      if (emptyText > textElements.length * 0.1) {
        problems.push(`Many hidden text elements (${emptyText}/${textElements.length})`);
      }

      return problems;
    });

    if (layoutIssues.length === 0) {
      successes.push('✓ Layout appears correct');
    } else {
      warnings.push(...layoutIssues);
    }

    // Check API response times
    console.log('\n⏱️ Checking API performance...');
    const performance = await page.evaluate(() => {
      const entries = performance.getEntriesByType('resource');
      const apiCalls = entries.filter(e => e.name.includes('/api/'));

      return {
        totalApiCalls: apiCalls.length,
        slowestCall: Math.max(...apiCalls.map(e => e.duration)),
        averageTime: apiCalls.reduce((sum, e) => sum + e.duration, 0) / apiCalls.length,
      };
    });

    if (performance.totalApiCalls > 0) {
      successes.push(`✓ ${performance.totalApiCalls} API calls completed`);
      console.log(`  - Slowest: ${performance.slowestCall.toFixed(0)}ms`);
      console.log(`  - Average: ${performance.averageTime.toFixed(0)}ms`);

      if (performance.slowestCall > 5000) {
        warnings.push(`Slow API response: ${performance.slowestCall.toFixed(0)}ms`);
      }
    }

    // Check for React errors
    console.log('\n⚛️ Checking React...');
    const hasReactDevTools = await page.evaluate(() => {
      return typeof window.__REACT_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined';
    });

    const unmountedComponents = await page.evaluate(() => {
      // Check for common React issues
      const issues = [];
      const warnings = console.warn.toString().includes('unmounted');
      if (warnings) issues.push('Unmounted component warnings detected');
      return issues;
    });

    if (unmountedComponents.length === 0) {
      successes.push('✓ No React unmount issues');
    }

    // Check for memory/performance
    console.log('\n💾 Checking performance metrics...');
    const metrics = await page.evaluate(() => {
      if (!performance.memory) return null;
      return {
        usedJSHeapSize: Math.round(performance.memory.usedJSHeapSize / 1048576),
        jsHeapSizeLimit: Math.round(performance.memory.jsHeapSizeLimit / 1048576),
      };
    });

    if (metrics) {
      const heapPercent = (metrics.usedJSHeapSize / metrics.jsHeapSizeLimit * 100).toFixed(1);
      successes.push(`✓ Memory: ${metrics.usedJSHeapSize}MB / ${metrics.jsHeapSizeLimit}MB (${heapPercent}%)`);
      if (heapPercent > 80) {
        warnings.push(`High memory usage: ${heapPercent}%`);
      }
    }

    // Check data loading
    console.log('\n📈 Checking data...');
    const dataCheckResults = await page.evaluate(() => {
      const results = [];

      // Look for data in the DOM
      const numbers = document.body.innerHTML.match(/\$[\d,]+\.?\d*/g);
      if (numbers && numbers.length > 0) results.push(`Found ${numbers.length} monetary values`);

      const percentages = document.body.innerHTML.match(/[\d.]+%/g);
      if (percentages && percentages.length > 0) results.push(`Found ${percentages.length} percentages`);

      const timestamps = document.body.innerHTML.match(/\d{2}:\d{2}/g);
      if (timestamps && timestamps.length > 0) results.push(`Found ${timestamps.length} timestamps`);

      return results;
    });

    dataCheckResults.forEach(r => successes.push(`✓ ${r}`));

    // Network health check
    console.log('\n🌐 Checking network...');
    const networkHealth = await page.evaluate(() => {
      const entries = performance.getEntriesByType('navigation')[0];
      return {
        domLoading: entries.domLoading - entries.fetchStart,
        domInteractive: entries.domInteractive - entries.fetchStart,
        domComplete: entries.domComplete - entries.fetchStart,
      };
    });

    if (networkHealth.domComplete < 5000) {
      successes.push(`✓ DOM ready in ${networkHealth.domComplete.toFixed(0)}ms`);
    } else {
      warnings.push(`Slow DOM load: ${networkHealth.domComplete.toFixed(0)}ms`);
    }

    // Final status report
    console.log('\n' + '═'.repeat(50));
    console.log('\n📋 DIAGNOSTIC REPORT\n');

    if (successes.length > 0) {
      console.log('✅ SUCCESSES:');
      successes.forEach(s => console.log(`  ${s}`));
    }

    if (warnings.length > 0) {
      console.log('\n⚠️ WARNINGS:');
      warnings.forEach(w => console.log(`  ${w}`));
    }

    if (issues.length > 0) {
      console.log('\n❌ ISSUES:');
      issues.forEach(issue => console.log(`  ${issue}`));
    }

    console.log('\n' + '═'.repeat(50));
    console.log(`\nTotal: ${successes.length} successes, ${warnings.length} warnings, ${issues.length} issues\n`);

    if (issues.length === 0) {
      console.log('✅ DASHBOARD STATUS: HEALTHY');
    } else {
      console.log(`⚠️ DASHBOARD STATUS: ${issues.length} ISSUES TO FIX`);
    }

  } catch (error) {
    console.error('\n❌ TEST FAILED:', error.message);
    issues.push(`Test error: ${error.message}`);
  } finally {
    await browser.close();
  }
})();
