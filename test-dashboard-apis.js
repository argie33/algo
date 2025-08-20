const axios = require("axios");

const API_BASE = "https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev";

// Test the dashboard APIs
async function testDashboardAPIs() {
  console.log("🧪 Testing Dashboard APIs with AWS endpoint...\n");

  const endpoints = [
    {
      name: "Market Summary",
      url: "/api/dashboard/market-summary",
      method: "GET",
    },
    {
      name: "Earnings Calendar (AAPL)",
      url: "/api/dashboard/earnings-calendar?symbol=AAPL",
      method: "GET",
    },
    {
      name: "Analyst Insights (AAPL)",
      url: "/api/dashboard/analyst-insights?symbol=AAPL",
      method: "GET",
    },
    {
      name: "Financial Highlights (AAPL)",
      url: "/api/dashboard/financial-highlights?symbol=AAPL",
      method: "GET",
    },
    {
      name: "Watchlist",
      url: "/api/dashboard/watchlist",
      method: "GET",
    },
    {
      name: "Signals",
      url: "/api/dashboard/signals",
      method: "GET",
    },
    {
      name: "Symbols",
      url: "/api/dashboard/symbols",
      method: "GET",
    },
    {
      name: "Portfolio",
      url: "/api/dashboard/portfolio",
      method: "GET",
    },
    {
      name: "News",
      url: "/api/dashboard/news",
      method: "GET",
    },
    {
      name: "Activity",
      url: "/api/dashboard/activity",
      method: "GET",
    },
    {
      name: "Calendar",
      url: "/api/dashboard/calendar",
      method: "GET",
    },
  ];

  for (const endpoint of endpoints) {
    try {
      console.log(`📡 Testing ${endpoint.name}...`);
      const fullUrl = `${API_BASE}${endpoint.url}`;
      console.log(`   URL: ${fullUrl}`);

      const response = await axios.get(fullUrl, {
        timeout: 30000,
        headers: {
          "Content-Type": "application/json",
        },
      });

      console.log(`   ✅ Status: ${response.status}`);
      console.log(
        `   📊 Data: ${JSON.stringify(response.data, null, 2).substring(0, 200)}...`
      );
      console.log(
        `   ⏱️  Response time: ${response.headers["x-response-time"] || "N/A"}`
      );

      if (response.data && response.data.success === false) {
        console.log(`   ⚠️  API returned success: false`);
      }
    } catch (error) {
      console.log(`   ❌ Error: ${error.message}`);
      if (error.response) {
        console.log(`   📋 Status: ${error.response.status}`);
        console.log(
          `   📄 Data: ${JSON.stringify(error.response.data, null, 2)}`
        );
      }
    }
    console.log(""); // Empty line for readability
  }
}

// Test health endpoint first
async function testHealth() {
  try {
    console.log("🏥 Testing API health endpoint...");
    const response = await axios.get(`${API_BASE}/health?quick=true`, {
      timeout: 10000,
    });
    console.log(`✅ Health check passed: ${response.status}`);
    console.log(`📊 Health data: ${JSON.stringify(response.data, null, 2)}`);
  } catch (error) {
    console.log(`❌ Health check failed: ${error.message}`);
  }
  console.log("");
}

// Run tests
async function runTests() {
  await testHealth();
  await testDashboardAPIs();
  console.log("🎉 Dashboard API testing complete!");
}

runTests().catch(console.error);
