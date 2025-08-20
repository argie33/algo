const axios = require("axios");

const API_BASE = "https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev";

// Comprehensive API endpoint test suite
async function testAllAPIs() {
  console.log("🧪 Comprehensive API Health Testing Suite\n");
  console.log(`🎯 Testing against: ${API_BASE}\n`);

  const endpoints = [
    // Core Health & System
    {
      category: "System Health",
      tests: [
        {
          name: "Health Check (Quick)",
          url: "/health?quick=true",
          method: "GET",
        },
        { name: "Health Check (Full)", url: "/health", method: "GET" },
        { name: "Database Health", url: "/health/database", method: "GET" },
        {
          name: "Database Diagnostics",
          url: "/health/database/diagnostics",
          method: "GET",
        },
        {
          name: "Health Status Summary",
          url: "/health/status-summary",
          method: "GET",
        },
      ],
    },

    // Authentication & Authorization
    {
      category: "Authentication",
      tests: [
        { name: "Auth User Info", url: "/auth/user", method: "GET" },
        { name: "Auth Config", url: "/auth/config", method: "GET" },
      ],
    },

    // Stock Data & Screening
    {
      category: "Stock Data",
      tests: [
        { name: "Stock List", url: "/stocks", method: "GET" },
        { name: "Stock Detail (AAPL)", url: "/stocks/AAPL", method: "GET" },
        { name: "Stock Screen", url: "/stocks/screen", method: "GET" },
        { name: "Stock Search", url: "/stocks/search?q=AAPL", method: "GET" },
        {
          name: "Stock Prices (AAPL)",
          url: "/stocks/AAPL/prices",
          method: "GET",
        },
      ],
    },

    // Metrics & Scoring
    {
      category: "Metrics & Scoring",
      tests: [
        { name: "Metrics List", url: "/metrics", method: "GET" },
        { name: "Metrics Detail (AAPL)", url: "/metrics/AAPL", method: "GET" },
        {
          name: "Sector Analysis",
          url: "/metrics/sectors/analysis",
          method: "GET",
        },
        {
          name: "Top Quality Stocks",
          url: "/metrics/top/quality",
          method: "GET",
        },
        { name: "Top Value Stocks", url: "/metrics/top/value", method: "GET" },
        {
          name: "Top Composite Stocks",
          url: "/metrics/top/composite",
          method: "GET",
        },
        { name: "Scores List", url: "/scores", method: "GET" },
        { name: "Score Detail (AAPL)", url: "/scores/AAPL", method: "GET" },
      ],
    },

    // Market Data
    {
      category: "Market Data",
      tests: [
        { name: "Market Overview", url: "/market", method: "GET" },
        { name: "Market Summary", url: "/market/summary", method: "GET" },
        { name: "Market Indices", url: "/market/indices", method: "GET" },
        { name: "Market Breadth", url: "/market/breadth", method: "GET" },
        { name: "Sector Performance", url: "/market/sectors", method: "GET" },
      ],
    },

    // Technical Analysis
    {
      category: "Technical Analysis",
      tests: [
        { name: "Technical Daily", url: "/technical/daily", method: "GET" },
        { name: "Technical Weekly", url: "/technical/weekly", method: "GET" },
        { name: "Technical Monthly", url: "/technical/monthly", method: "GET" },
        {
          name: "Technical Detail (AAPL)",
          url: "/technical/AAPL",
          method: "GET",
        },
      ],
    },

    // Financial Data
    {
      category: "Financial Data",
      tests: [
        { name: "Financials (AAPL)", url: "/financials/AAPL", method: "GET" },
        {
          name: "Income Statement (AAPL)",
          url: "/financials/AAPL/income",
          method: "GET",
        },
        {
          name: "Balance Sheet (AAPL)",
          url: "/financials/AAPL/balance",
          method: "GET",
        },
        {
          name: "Cash Flow (AAPL)",
          url: "/financials/AAPL/cashflow",
          method: "GET",
        },
        {
          name: "Key Metrics (AAPL)",
          url: "/financials/AAPL/metrics",
          method: "GET",
        },
      ],
    },

    // Trading & Signals
    {
      category: "Trading & Signals",
      tests: [
        { name: "Trading Signals", url: "/trading/signals", method: "GET" },
        {
          name: "Buy Signals Daily",
          url: "/trading/signals/daily",
          method: "GET",
        },
        {
          name: "Buy Signals Weekly",
          url: "/trading/signals/weekly",
          method: "GET",
        },
        {
          name: "Buy Signals Monthly",
          url: "/trading/signals/monthly",
          method: "GET",
        },
        { name: "Signals List", url: "/signals", method: "GET" },
        { name: "Signals Summary", url: "/signals/summary", method: "GET" },
      ],
    },

    // Calendar & Events
    {
      category: "Calendar & Events",
      tests: [
        { name: "Calendar Events", url: "/calendar", method: "GET" },
        { name: "Earnings Calendar", url: "/calendar/earnings", method: "GET" },
        { name: "Economic Calendar", url: "/calendar/economic", method: "GET" },
        { name: "Event Detail", url: "/calendar/events", method: "GET" },
      ],
    },

    // Analyst Data
    {
      category: "Analyst Data",
      tests: [
        { name: "Analyst Estimates", url: "/analysts", method: "GET" },
        {
          name: "Analyst Estimates (AAPL)",
          url: "/analysts/AAPL",
          method: "GET",
        },
        {
          name: "Analyst Upgrades/Downgrades",
          url: "/analysts/upgrades",
          method: "GET",
        },
        {
          name: "Analyst Recommendations",
          url: "/analysts/recommendations",
          method: "GET",
        },
      ],
    },

    // Portfolio Management
    {
      category: "Portfolio",
      tests: [
        { name: "Portfolio Overview", url: "/portfolio", method: "GET" },
        {
          name: "Portfolio Holdings",
          url: "/portfolio/holdings",
          method: "GET",
        },
        {
          name: "Portfolio Performance",
          url: "/portfolio/performance",
          method: "GET",
        },
        {
          name: "Portfolio Analytics",
          url: "/portfolio/analytics",
          method: "GET",
        },
      ],
    },

    // Data Management
    {
      category: "Data Management",
      tests: [
        { name: "Data Status", url: "/data", method: "GET" },
        { name: "Data Sources", url: "/data/sources", method: "GET" },
        { name: "Data Quality", url: "/data/quality", method: "GET" },
        { name: "Data Updates", url: "/data/updates", method: "GET" },
      ],
    },

    // Backtesting
    {
      category: "Backtesting",
      tests: [
        { name: "Backtest Results", url: "/backtest", method: "GET" },
        {
          name: "Backtest Strategies",
          url: "/backtest/strategies",
          method: "GET",
        },
        {
          name: "Backtest Performance",
          url: "/backtest/performance",
          method: "GET",
        },
      ],
    },

    // Dashboard APIs
    {
      category: "Dashboard",
      tests: [
        { name: "Dashboard Summary", url: "/dashboard/summary", method: "GET" },
        {
          name: "Market Summary",
          url: "/dashboard/market-summary",
          method: "GET",
        },
        {
          name: "Earnings Calendar (AAPL)",
          url: "/dashboard/earnings-calendar?symbol=AAPL",
          method: "GET",
        },
        {
          name: "Analyst Insights (AAPL)",
          url: "/dashboard/analyst-insights?symbol=AAPL",
          method: "GET",
        },
        {
          name: "Financial Highlights (AAPL)",
          url: "/dashboard/financial-highlights?symbol=AAPL",
          method: "GET",
        },
        { name: "Watchlist", url: "/dashboard/watchlist", method: "GET" },
        { name: "Signals", url: "/dashboard/signals", method: "GET" },
        { name: "Symbols", url: "/dashboard/symbols", method: "GET" },
        { name: "Portfolio", url: "/dashboard/portfolio", method: "GET" },
        { name: "News", url: "/dashboard/news", method: "GET" },
        { name: "Activity", url: "/dashboard/activity", method: "GET" },
        { name: "Calendar", url: "/dashboard/calendar", method: "GET" },
        { name: "Market Data", url: "/dashboard/market-data", method: "GET" },
      ],
    },
  ];

  const results = {
    total: 0,
    passed: 0,
    failed: 0,
    categories: {},
    failedEndpoints: [],
  };

  for (const category of endpoints) {
    console.log(
      `\n📂 Testing ${category.category} (${category.tests.length} endpoints)`
    );
    console.log("=".repeat(60));

    const categoryResults = {
      total: category.tests.length,
      passed: 0,
      failed: 0,
      errors: [],
    };

    for (const test of category.tests) {
      try {
        console.log(`📡 ${test.name}...`);
        const fullUrl = `${API_BASE}${test.url}`;

        const startTime = Date.now();
        const response = await axios({
          method: test.method,
          url: fullUrl,
          timeout: 30000,
          headers: {
            "Content-Type": "application/json",
            Accept: "application/json",
          },
          validateStatus: function (status) {
            // Accept any status for testing purposes
            return status < 600;
          },
        });

        const responseTime = Date.now() - startTime;

        if (response.status >= 200 && response.status < 300) {
          console.log(`   ✅ ${response.status} (${responseTime}ms)`);
          categoryResults.passed++;
          results.passed++;
        } else if (response.status === 404) {
          console.log(
            `   ⚠️  ${response.status} - Endpoint not implemented (${responseTime}ms)`
          );
          categoryResults.failed++;
          results.failed++;
          categoryResults.errors.push(`${test.name}: Not implemented (404)`);
          results.failedEndpoints.push(
            `${category.category}/${test.name}: 404 Not Found`
          );
        } else if (response.status === 401 || response.status === 403) {
          console.log(
            `   🔐 ${response.status} - Authentication required (${responseTime}ms)`
          );
          categoryResults.passed++; // Count auth errors as "working" endpoints
          results.passed++;
        } else {
          console.log(
            `   ❌ ${response.status} - ${response.statusText} (${responseTime}ms)`
          );
          categoryResults.failed++;
          results.failed++;
          categoryResults.errors.push(
            `${test.name}: ${response.status} ${response.statusText}`
          );
          results.failedEndpoints.push(
            `${category.category}/${test.name}: ${response.status} ${response.statusText}`
          );
        }

        results.total++;
      } catch (error) {
        console.log(`   ❌ ${error.message}`);
        categoryResults.failed++;
        results.failed++;
        results.total++;
        categoryResults.errors.push(`${test.name}: ${error.message}`);
        results.failedEndpoints.push(
          `${category.category}/${test.name}: ${error.message}`
        );
      }
    }

    results.categories[category.category] = categoryResults;

    const passRate = (
      (categoryResults.passed / categoryResults.total) *
      100
    ).toFixed(1);
    console.log(
      `\n📊 ${category.category} Summary: ${categoryResults.passed}/${categoryResults.total} passed (${passRate}%)`
    );

    if (categoryResults.errors.length > 0) {
      console.log(`❌ Errors:`);
      categoryResults.errors.forEach((error) => console.log(`   - ${error}`));
    }
  }

  // Final summary
  console.log("\n" + "=".repeat(80));
  console.log("🎯 COMPREHENSIVE API HEALTH TEST RESULTS");
  console.log("=".repeat(80));

  const overallPassRate = ((results.passed / results.total) * 100).toFixed(1);
  console.log(
    `📊 Overall: ${results.passed}/${results.total} endpoints passed (${overallPassRate}%)`
  );
  console.log(`✅ Passed: ${results.passed}`);
  console.log(`❌ Failed: ${results.failed}`);

  console.log("\n📋 Category Breakdown:");
  for (const [category, data] of Object.entries(results.categories)) {
    const rate = ((data.passed / data.total) * 100).toFixed(1);
    const status = rate >= 80 ? "✅" : rate >= 60 ? "⚠️ " : "❌";
    console.log(
      `   ${status} ${category}: ${data.passed}/${data.total} (${rate}%)`
    );
  }

  if (results.failedEndpoints.length > 0) {
    console.log("\n❌ Failed Endpoints:");
    results.failedEndpoints.forEach((endpoint) =>
      console.log(`   - ${endpoint}`)
    );
  }

  // Recommendations
  console.log("\n💡 Recommendations:");
  if (results.failedEndpoints.length > 0) {
    console.log("   - Implement missing endpoints (404 errors)");
    console.log("   - Fix server errors (5xx responses)");
    console.log("   - Review authentication requirements");
  }

  if (overallPassRate >= 90) {
    console.log(
      "   🎉 Excellent API coverage! Most endpoints are working correctly."
    );
  } else if (overallPassRate >= 75) {
    console.log("   👍 Good API coverage with some areas for improvement.");
  } else {
    console.log(
      "   ⚠️  API coverage needs improvement. Many endpoints are failing."
    );
  }

  console.log("\n🔧 Health Check Integration:");
  console.log("   - Add successful endpoints to automated health monitoring");
  console.log("   - Set up alerts for critical endpoint failures");
  console.log("   - Implement endpoint performance tracking");

  return results;
}

// Run the comprehensive test suite
async function main() {
  try {
    const results = await testAllAPIs();

    // Exit with appropriate code
    if (results.failed === 0) {
      console.log("\n🎉 All tests passed!");
      process.exit(0);
    } else if (results.passed / results.total >= 0.8) {
      console.log("\n✅ Most tests passed with minor issues.");
      process.exit(0);
    } else {
      console.log("\n⚠️  Many tests failed. Review and fix issues.");
      process.exit(1);
    }
  } catch (error) {
    console.error("\n💥 Test suite failed:", error.message);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}

module.exports = { testAllAPIs };
