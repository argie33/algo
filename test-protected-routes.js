const { chromium } = require('playwright');

async function testProtectedRoutes() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const issues = [];

  // Pages that require authentication
  const protectedPages = [
    { name: 'Portfolio', url: '/app/portfolio' },
    { name: 'Trade Tracker', url: '/app/trades' },
    { name: 'Performance', url: '/app/performance' },
    { name: 'Portfolio Optimizer', url: '/app/optimizer' },
    { name: 'Settings', url: '/app/settings' },
    { name: 'Service Health', url: '/app/health' },
    { name: 'Notifications', url: '/app/notifications' },
    { name: 'Audit Trail', url: '/app/audit' },
  ];

  console.log('🔐 TESTING PROTECTED/ADMIN ROUTES\n');
  console.log('='.repeat(60));

  for (const page_info of protectedPages) {
    const errors = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    try {
      const response = await page.goto(`http://localhost:5173${page_info.url}`, {
        waitUntil: 'domcontentloaded',
        timeout: 8000
      });

      const content = await page.evaluate(() => {
        return {
          hasErrorBoundary: !!document.querySelector('[role="alert"]'),
          hasAuthForm: !!document.querySelector('input[type="password"]'),
          hasContent: document.body.textContent.length > 500,
          hasLoginPrompt: document.body.textContent.includes('Sign In') || document.body.textContent.includes('Login'),
          hasAccessDenied: document.body.textContent.includes('Access Denied') || document.body.textContent.includes('not authorized')
        };
      });

      const status = response.status();
      let issue = '';

      if (content.hasLoginPrompt || content.hasAuthForm) {
        issue = '⚠️  REQUIRES AUTH - Not implemented yet';
      } else if (content.hasAccessDenied) {
        issue = '❌ ACCESS DENIED - Auth issue';
      } else if (!content.hasContent) {
        issue = '⚠️  NO CONTENT - Page may not have data';
      } else if (errors.length > 0) {
        issue = `❌ ${errors.length} ERRORS - ${errors[0].substring(0, 50)}`;
      } else {
        issue = '✅ WORKING';
      }

      console.log(`${page_info.name.padEnd(25)} │ ${issue}`);

      if (issue !== '✅ WORKING') {
        issues.push({
          page: page_info.name,
          url: page_info.url,
          issue,
          errors: errors.length,
          requiresAuth: content.hasLoginPrompt || content.hasAuthForm
        });
      }

    } catch (error) {
      console.log(`${page_info.name.padEnd(25)} │ ❌ TIMEOUT - ${error.message.substring(0, 40)}`);
      issues.push({
        page: page_info.name,
        url: page_info.url,
        issue: 'TIMEOUT',
        errors: 1
      });
    }
  }

  console.log('='.repeat(60));
  console.log(`\n⚠️  ISSUES FOUND: ${issues.length}`);
  issues.forEach(issue => {
    console.log(`  • ${issue.page}: ${issue.issue}`);
  });

  await browser.close();
  return issues;
}

testProtectedRoutes().catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
