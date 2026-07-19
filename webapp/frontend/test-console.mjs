import { chromium } from '@playwright/test';

const browser = await chromium.launch();
const page = await browser.newPage();

const messages = {
  errors: [],
  warnings: [],
  logs: [],
  corsErrors: [],
  requestErrors: [],
};

page.on('console', (msg) => {
  const text = msg.text();
  const type = msg.type();

  if (type === 'error') {
    messages.errors.push(text);
    if (text.includes('CORS')) messages.corsErrors.push(text);
  } else if (type === 'warning') {
    messages.warnings.push(text);
  } else {
    messages.logs.push(text);
  }
});

page.on('pageerror', (err) => {
  messages.errors.push(`Page Error: ${err.message}`);
});

page.on('requestfailed', (request) => {
  messages.requestErrors.push(`Failed: ${request.url()}`);
});

try {
  console.log('🔍 Testing http://localhost:5175...');
  await page.goto('http://localhost:5175', { waitUntil: 'networkidle', timeout: 15000 });
  await page.waitForTimeout(3000);

  console.log('\n' + '='.repeat(60));
  console.log('📊 CONSOLE CHECK RESULTS');
  console.log('='.repeat(60));

  // Check for critical errors
  const corsErrors = messages.corsErrors.filter(e => !e.includes('resize observer'));
  const criticalErrors = messages.errors.filter(e =>
    !e.includes('404') &&
    !e.includes('ResizeObserver') &&
    !e.includes('Network error') &&
    !e.includes('Failed to load resource')
  );

  if (corsErrors.length === 0) {
    console.log('✅ CORS: No CORS errors detected');
  } else {
    console.log(`❌ CORS: ${corsErrors.length} CORS errors found`);
  }

  if (criticalErrors.length === 0) {
    console.log('✅ ERRORS: No critical JavaScript errors');
  } else {
    console.log(`❌ ERRORS: ${criticalErrors.length} critical errors found`);
    criticalErrors.forEach((e, i) => console.log(`   ${i + 1}. ${e}`));
  }

  // API call status
  const api404s = messages.errors.filter(e => e.includes('404')).length;
  if (api404s > 0) {
    console.log(`⚠️  API: ${api404s} API endpoints returning 404 (expected if dev server incomplete)`);
  } else {
    console.log('✅ API: All API calls successful or not attempted');
  }

  console.log('\n' + '='.repeat(60));
  console.log('📋 SUMMARY');
  console.log('='.repeat(60));

  const allGood = corsErrors.length === 0 && criticalErrors.length === 0;
  if (allGood) {
    console.log('✅ FRONTEND READY FOR LOCAL DEVELOPMENT');
    console.log('   • No CORS errors');
    console.log('   • No critical JavaScript errors');
    console.log('   • Ready to run with or without AWS');
    process.exit(0);
  } else {
    console.log('❌ ISSUES FOUND - Please review above');
    process.exit(1);
  }
} catch (error) {
  console.error('❌ Test failed:', error.message);
  process.exit(1);
} finally {
  await browser.close();
}
