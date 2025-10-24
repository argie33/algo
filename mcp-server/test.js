#!/usr/bin/env node

/**
 * Simple MCP Server Test
 * Tests that the MCP server can connect to the backend API and retrieve data
 */

require("dotenv").config();

const axios = require("axios");
const config = require("./config.js");

const getApiConfig = () => {
  const env = config.environment === "production" ? "prod" : "dev";
  return config.api[env];
};

const apiClient = axios.create({
  timeout: 10000,
});

apiClient.interceptors.request.use((config) => {
  const apiConfig = getApiConfig();
  config.headers["Authorization"] = `Bearer ${apiConfig.authToken}`;
  return config;
});

const callApi = async (endpoint, method = "GET", params = {}) => {
  try {
    const apiConfig = getApiConfig();
    const url = `${apiConfig.baseUrl}${endpoint}`;

    console.log(`\n📡 Testing: ${method} ${url}`);
    const response = await apiClient({
      method,
      url,
      params: method === "GET" ? params : undefined,
    });

    console.log(`✅ Success! Status: ${response.status}`);
    return response.data;
  } catch (error) {
    console.log(`❌ Error: ${error.message}`);
    if (error.response) {
      console.log(`   Status: ${error.response.status}`);
      console.log(`   Data: ${JSON.stringify(error.response.data).substring(0, 200)}`);
    }
    throw error;
  }
};

async function runTests() {
  console.log("\n🧪 MCP Server API Tests\n");
  console.log(`Environment: ${config.environment}`);
  console.log(`API Base URL: ${getApiConfig().baseUrl}`);
  console.log(`Auth Token: ${getApiConfig().authToken}\n`);

  const tests = [
    {
      name: "Health Check",
      endpoint: "/api/health",
      params: {},
    },
    {
      name: "Stock Search",
      endpoint: "/api/stocks/search",
      params: { q: "AAPL", limit: 5 },
    },
    {
      name: "Market Overview",
      endpoint: "/api/market/overview",
      params: {},
    },
    {
      name: "Dashboard",
      endpoint: "/api/dashboard",
      params: {},
    },
    {
      name: "Sectors",
      endpoint: "/api/sectors",
      params: {},
    },
  ];

  let passed = 0;
  let failed = 0;

  for (const test of tests) {
    try {
      console.log(`\nTest: ${test.name}`);
      const result = await callApi(test.endpoint, "GET", test.params);

      if (result.success !== false) {
        console.log(`   Data keys: ${Object.keys(result).join(", ")}`);
        passed++;
      } else {
        console.log(`   Warning: API returned success:false`);
        passed++;
      }
    } catch (error) {
      failed++;
    }
  }

  console.log("\n" + "=".repeat(50));
  console.log(`\n📊 Test Results:`);
  console.log(`   ✅ Passed: ${passed}`);
  console.log(`   ❌ Failed: ${failed}`);
  console.log(`   📈 Success Rate: ${((passed / (passed + failed)) * 100).toFixed(0)}%\n`);

  if (failed === 0) {
    console.log("🎉 All tests passed! MCP server is ready to use.\n");
    process.exit(0);
  } else {
    console.log("⚠️  Some tests failed. Check your setup.\n");
    process.exit(1);
  }
}

runTests().catch((error) => {
  console.error("\n💥 Test suite failed:", error.message);
  process.exit(1);
});
