/* eslint-disable node/no-unpublished-require */
const axios = require("axios");

const BACKEND_URL = "http://localhost:3001";
const FRONTEND_URL = "http://localhost:5173";

// Comprehensive API endpoints to test
const apiEndpoints = [
  { path: "/api/health", name: "Health Check" },
  { path: "/api/stocks", name: "Stocks List" },
  { path: "/api/stocks/popular", name: "Popular Stocks" },
  { path: "/api/market/overview", name: "Market Overview" },
  { path: "/api/sentiment/analysis?symbol=AAPL", name: "Sentiment Analysis" },
  { path: "/api/metrics/market", name: "Market Metrics" },
  { path: "/api/metrics/performance", name: "Performance Metrics" },
  {
    path: "/api/financials/statements?symbol=AAPL",
    name: "Financial Statements",
  },
  { path: "/api/financials/ratios?symbol=AAPL", name: "Financial Ratios" },
  { path: "/api/price/AAPL", name: "Stock Price Data" },
  { path: "/api/stocks/AAPL/financials", name: "Stock Financials" },
  { path: "/api/data/sources", name: "Data Sources" },
  { path: "/api/data/status", name: "Data Status" },
  { path: "/api/portfolio/holdings", name: "Portfolio Holdings" },
  { path: "/api/risk/analysis", name: "Risk Analysis" },
  {
    path: "/api/screener/screen?criteria=market_cap>1B",
    name: "Stock Screener",
  },
];

// Frontend pages to test
const frontendPages = [
  { path: "/", name: "Home Page" },
  { path: "/dashboard", name: "Dashboard" },
  { path: "/portfolio", name: "Portfolio" },
  { path: "/market", name: "Market" },
  { path: "/analysis", name: "Analysis" },
];

async function testEndpoint(url, endpoint) {
  try {
    const start = Date.now();
    const response = await axios.get(`${url}${endpoint.path}`, {
      timeout: 15000,
      validateStatus: (status) => status < 500,
    });
    const duration = Date.now() - start;

    const hasData =
      response.data &&
      (Object.keys(response.data).length > 0 ||
        (Array.isArray(response.data) && response.data.length > 0));

    if (response.status === 200 && hasData) {
      console.log(`✅ ${response.status} - ${duration}ms - ${endpoint.name}`);
      return { success: true, status: response.status, duration };
    } else if (response.status === 200) {
      console.log(
        `⚠️  ${response.status} - ${duration}ms - ${endpoint.name} (Empty data)`
      );
      return {
        success: false,
        status: response.status,
        duration,
        issue: "Empty data",
      };
    } else {
      console.log(`❌ ${response.status} - ${duration}ms - ${endpoint.name}`);
      return { success: false, status: response.status, duration };
    }
  } catch (error) {
    if (error.code === "ECONNREFUSED") {
      console.log(`🚫 CONN - Service unavailable - ${endpoint.name}`);
      return {
        success: false,
        status: "ECONNREFUSED",
        issue: "Service unavailable",
      };
    } else if (error.response) {
      console.log(
        `❌ ${error.response.status} - ${endpoint.name} - ${error.response.data?.error || error.message}`
      );
      return {
        success: false,
        status: error.response.status,
        error: error.message,
      };
    } else {
      console.log(`💥 ERROR - ${endpoint.name} - ${error.message}`);
      return { success: false, status: "ERROR", error: error.message };
    }
  }
}

async function testFrontendPage(url, page) {
  try {
    const start = Date.now();
    const response = await axios.get(`${url}${page.path}`, {
      timeout: 10000,
      headers: { Accept: "text/html,application/xhtml+xml,application/xml" },
    });
    const duration = Date.now() - start;

    if (response.status === 200) {
      console.log(
        `✅ ${response.status} - ${duration}ms - Frontend ${page.name}`
      );
      return { success: true, status: response.status, duration };
    } else {
      console.log(
        `❌ ${response.status} - ${duration}ms - Frontend ${page.name}`
      );
      return { success: false, status: response.status, duration };
    }
  } catch (error) {
    console.log(`❌ Frontend ${page.name} - ${error.message}`);
    return { success: false, status: "ERROR", error: error.message };
  }
}

async function main() {
  console.log("🚀 COMPREHENSIVE SITE HEALTH CHECK\n");

  console.log("📊 Testing Backend APIs...\n");
  const apiResults = [];
  for (const endpoint of apiEndpoints) {
    const result = await testEndpoint(BACKEND_URL, endpoint);
    apiResults.push({ ...endpoint, ...result });
  }

  console.log("\n🌐 Testing Frontend Pages...\n");
  const frontendResults = [];
  for (const page of frontendPages) {
    const result = await testFrontendPage(FRONTEND_URL, page);
    frontendResults.push({ ...page, ...result });
  }

  // Summary
  console.log("\n📋 COMPREHENSIVE HEALTH REPORT:");

  const apiSuccessful = apiResults.filter((r) => r.success);
  const apiFailed = apiResults.filter((r) => !r.success);

  console.log(`\n🔧 Backend APIs:`);
  console.log(
    `✅ Working: ${apiSuccessful.length}/${apiResults.length} (${((apiSuccessful.length / apiResults.length) * 100).toFixed(1)}%)`
  );
  console.log(
    `❌ Issues: ${apiFailed.length}/${apiResults.length} (${((apiFailed.length / apiResults.length) * 100).toFixed(1)}%)`
  );

  const frontendSuccessful = frontendResults.filter((r) => r.success);
  const frontendFailed = frontendResults.filter((r) => !r.success);

  console.log(`\n🌐 Frontend Pages:`);
  console.log(
    `✅ Working: ${frontendSuccessful.length}/${frontendResults.length} (${((frontendSuccessful.length / frontendResults.length) * 100).toFixed(1)}%)`
  );
  console.log(
    `❌ Issues: ${frontendFailed.length}/${frontendResults.length} (${((frontendFailed.length / frontendResults.length) * 100).toFixed(1)}%)`
  );

  const totalSuccessful = apiSuccessful.length + frontendSuccessful.length;
  const totalItems = apiResults.length + frontendResults.length;

  console.log(
    `\n🎯 OVERALL HEALTH SCORE: ${totalSuccessful}/${totalItems} (${((totalSuccessful / totalItems) * 100).toFixed(1)}%)`
  );

  if (apiFailed.length > 0) {
    console.log("\n🔧 API ISSUES TO ADDRESS:");
    apiFailed.forEach((f) => {
      console.log(
        `   ${f.status} - ${f.name}: ${f.issue || f.error || "Unknown issue"}`
      );
    });
  }

  if (frontendFailed.length > 0) {
    console.log("\n🌐 FRONTEND ISSUES TO ADDRESS:");
    frontendFailed.forEach((f) => {
      console.log(`   ${f.status} - ${f.name}: ${f.error || "Unknown issue"}`);
    });
  }

  if (totalSuccessful === totalItems) {
    console.log("\n🎉 SITE FULLY OPERATIONAL!");
    console.log("✅ All systems functioning correctly");
    console.log("🚀 Site ready for production use");
  } else {
    console.log(
      `\n⚠️  ${totalItems - totalSuccessful} issues require attention`
    );
  }

  // Performance summary
  const avgApiTime =
    apiSuccessful.reduce((sum, r) => sum + (r.duration || 0), 0) /
    (apiSuccessful.length || 1);
  const avgFrontendTime =
    frontendSuccessful.reduce((sum, r) => sum + (r.duration || 0), 0) /
    (frontendSuccessful.length || 1);

  console.log(`\n⚡ PERFORMANCE METRICS:`);
  console.log(`   Backend APIs: ${Math.round(avgApiTime)}ms average`);
  console.log(`   Frontend Pages: ${Math.round(avgFrontendTime)}ms average`);
}

main().catch(console.error);
