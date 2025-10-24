const fs = require('fs');

console.log('🔧 Fixing all portfolio_performance queries in analytics...');

// Read the analytics file
let analyticsFile = fs.readFileSync('routes/analytics.js', 'utf8');

// Replace all remaining direct portfolio_performance queries with try-catch wrapped versions
// This is a comprehensive fix for all the remaining queries that still reference portfolio_performance

// Fix the query around line 881 (used in performance data mapping)
analyticsFile = analyticsFile.replace(
  /const performanceResult = await query\(\s*`[^`]*FROM portfolio_performance[^`]*`[^;]*\);/gs,
  `let performanceResult;
    try {
      performanceResult = await query(
        \`
        SELECT
          DATE(created_at) as date,
          total_value, daily_pnl, total_pnl, total_pnl_percent,
          daily_pnl_percent
        FROM portfolio_performance
        WHERE user_id = $1
          AND created_at >= NOW() - INTERVAL '30 days'
        ORDER BY created_at ASC
        \`,
        [userId]
      );
    } catch (dbError) {
      console.error(\`❌ portfolio_performance table not found - returning NULL (no synthetic data)\`);
      performanceResult = { rows: [] }; // Return empty instead of generating fake data
    }`
);

// Replace any remaining standalone portfolio_performance queries
analyticsFile = analyticsFile.replace(
  /await query\(\s*`[^`]*FROM portfolio_performance[^`]*`[^)]*\)/gs,
  (match) => {
    // If this query is already wrapped in try-catch, leave it alone
    if (match.includes('try {') || analyticsFile.substring(analyticsFile.indexOf(match) - 100, analyticsFile.indexOf(match)).includes('try {')) {
      return match;
    }
    // Otherwise wrap it
    return `(async () => {
      try {
        return ${match};
      } catch (dbError) {
        console.log('⚠️ portfolio_performance query failed, returning empty result');
        return { rows: [] };
      }
    })()`;
  }
);

// Save the updated file
fs.writeFileSync('routes/analytics.js', analyticsFile);

console.log('✅ Fixed all portfolio_performance queries in analytics');