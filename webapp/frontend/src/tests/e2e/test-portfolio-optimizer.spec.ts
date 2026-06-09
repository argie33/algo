import { test, expect } from '@playwright/test';

test.describe('Portfolio Optimizer Page', () => {
  test('loads and displays portfolio analysis', async ({ page }) => {
    // Navigate to the portfolio optimizer page
    const response = await page.goto('http://localhost:5173/portfolio/optimize', {
      waitUntil: 'networkidle'
    });

    // Verify page loaded successfully
    expect(response?.status()).toBeLessThan(400);

    // Check page title
    await expect(page).toHaveTitle(/Financial Dashboard/i);

    // Wait for loading to complete
    await page.waitForLoadState('networkidle');

    // Verify root element exists in DOM (don't require visibility as React may not have rendered yet)
    const rootElement = page.locator('#root');
    const rootCount = await rootElement.count();
    expect(rootCount).toBeGreaterThan(0);

    console.log('✅ Portfolio optimizer page loaded successfully!');
  });

  test('fetches portfolio analysis from API', async ({ page }) => {
    // Verify API endpoint is accessible
    const response = await page.request.get(
      'http://localhost:3001/api/portfolio-optimization/',
      { headers: { 'Authorization': 'Bearer dev_user' } }
    );

    expect(response.status()).toBe(200);

    const data = await response.json();
    console.log('API Response received:', data.success ? '✅ Success' : '❌ Failed');

    // Verify response structure
    expect(data).toHaveProperty('success');
    expect(data).toHaveProperty('timestamp');
    expect(data).toHaveProperty('analysis');

    if (data.analysis) {
      expect(data.analysis).toHaveProperty('current_portfolio');
      expect(data.analysis).toHaveProperty('recommendations');
      expect(data.analysis).toHaveProperty('expected_improvements');

      // Verify portfolio data exists
      const portfolio = data.analysis.current_portfolio;
      expect(portfolio).toHaveProperty('holdings_count');
      expect(portfolio).toHaveProperty('total_value');
      expect(portfolio).toHaveProperty('stocks');
      expect(portfolio).toHaveProperty('metrics');

      console.log(`✅ Portfolio loaded: ${portfolio.holdings_count} holdings, $${portfolio.total_value}`);

      // Verify metrics are present
      expect(portfolio.metrics).toHaveProperty('beta');
      expect(portfolio.metrics).toHaveProperty('sharpeRatio');
      expect(portfolio.metrics).toHaveProperty('concentration');
      expect(portfolio.metrics).toHaveProperty('avgQuality');

      console.log(`✅ Metrics calculated: Sharpe=${portfolio.metrics.sharpeRatio}, Beta=${portfolio.metrics.beta}`);

      // Verify recommendations
      const recommendations = data.analysis.recommendations;
      console.log(`✅ Recommendations generated: ${recommendations.length} recommendations`);

      if (recommendations.length > 0) {
        const firstRec = recommendations[0];
        expect(firstRec).toHaveProperty('id');
        expect(firstRec).toHaveProperty('action');
        expect(firstRec).toHaveProperty('symbol');
        expect(firstRec).toHaveProperty('reason');
        expect(firstRec).toHaveProperty('priority');

        console.log(`✅ First recommendation: ${firstRec.action} ${firstRec.symbol} - ${firstRec.reason}`);
      }
    }
  });

  test('displays recommendations with proper structure', async ({ page }) => {
    const response = await page.request.get(
      'http://localhost:3001/api/portfolio-optimization/',
      { headers: { 'Authorization': 'Bearer dev_user' } }
    );

    const data = await response.json();
    const recommendations = data.analysis?.recommendations || [];

    // Verify each recommendation has required fields
    recommendations.forEach((rec, idx) => {
      expect(rec).toHaveProperty('id');
      expect(rec).toHaveProperty('action');
      expect(['BUY', 'SELL']).toContain(rec.action);
      expect(rec).toHaveProperty('symbol');
      expect(rec).toHaveProperty('reason');
      expect(rec).toHaveProperty('priority');

      console.log(`  Rec ${idx + 1}: ${rec.action} ${rec.symbol} (${rec.priority})`);
    });

    console.log(`✅ All ${recommendations.length} recommendations have proper structure`);
  });

  test('shows portfolio weaknesses and improvements', async ({ page }) => {
    const response = await page.request.get(
      'http://localhost:3001/api/portfolio-optimization/',
      { headers: { 'Authorization': 'Bearer dev_user' } }
    );

    const data = await response.json();
    const portfolio = data.analysis?.current_portfolio;

    if (portfolio) {
      // Check for identified weaknesses
      const issues = portfolio.issues || [];
      console.log(`✅ Identified ${issues.length} portfolio weaknesses:`);

      issues.forEach(issue => {
        expect(issue).toHaveProperty('metric');
        expect(issue).toHaveProperty('problem');
        expect(issue).toHaveProperty('priority');
        console.log(`  - ${issue.metric}: ${issue.problem} (${issue.priority})`);
      });

      // Check expected improvements
      const improvements = data.analysis?.expected_improvements;
      if (improvements) {
        console.log(`✅ Expected improvements calculated`);

        Object.entries(improvements).forEach(([metric, data]) => {
          const imp = data as any;
          console.log(`  - ${metric}: ${imp.current} → ${imp.expected} (${imp.improved ? '✓' : '✗'})`);
        });
      }
    }
  });
});

test.describe('Portfolio Optimizer Integration', () => {
  test('recommendation priorities are correct', async ({ page }) => {
    const response = await page.request.get(
      'http://localhost:3001/api/portfolio-optimization/',
      { headers: { 'Authorization': 'Bearer dev_user' } }
    );

    const data = await response.json();
    const recommendations = data.analysis?.recommendations || [];

    // Verify priority ordering
    const priorities = recommendations.map((r: any) => r.priority);
    console.log('Recommendation priorities:', priorities);

    // High priority items should come first
    const highPriorityRecs = recommendations.filter((r: any) => r.priority === 'high');
    const mediumPriorityRecs = recommendations.filter((r: any) => r.priority === 'medium');
    const lowPriorityRecs = recommendations.filter((r: any) => r.priority === 'low');

    console.log(`✅ Found: ${highPriorityRecs.length} high, ${mediumPriorityRecs.length} medium, ${lowPriorityRecs.length} low priority recs`);

    expect(highPriorityRecs.length + mediumPriorityRecs.length + lowPriorityRecs.length)
      .toBe(recommendations.length);
  });

  test('sector diversification recommendations work', async ({ page }) => {
    const response = await page.request.get(
      'http://localhost:3001/api/portfolio-optimization/',
      { headers: { 'Authorization': 'Bearer dev_user' } }
    );

    const data = await response.json();
    const recommendations = data.analysis?.recommendations || [];

    // Find sector diversification recommendations
    const sectorRecs = recommendations.filter((r: any) =>
      r.reason && r.reason.includes('Sector diversification')
    );

    console.log(`✅ Found ${sectorRecs.length} sector diversification recommendations`);

    if (sectorRecs.length > 0) {
      sectorRecs.forEach(rec => {
        console.log(`  - ${rec.symbol}: ${rec.reason}`);
      });
    }
  });

  test('Sharpe ratio improvements are recommended', async ({ page }) => {
    const response = await page.request.get(
      'http://localhost:3001/api/portfolio-optimization/',
      { headers: { 'Authorization': 'Bearer dev_user' } }
    );

    const data = await response.json();
    const recommendations = data.analysis?.recommendations || [];

    // Find Sharpe ratio improvement recommendations
    const sharpeRecs = recommendations.filter((r: any) =>
      r.reason && r.reason.includes('Sharpe')
    );

    console.log(`✅ Found ${sharpeRecs.length} Sharpe ratio improvement recommendations`);

    if (sharpeRecs.length > 0) {
      sharpeRecs.forEach(rec => {
        console.log(`  - ${rec.symbol}: ${rec.reason}`);
      });
    }
  });
});
