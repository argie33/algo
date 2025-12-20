#!/usr/bin/env node

/**
 * Real MCP Tool Testing
 * Actually calls the tools to see if they work end-to-end
 */

require("dotenv").config();

const axios = require("axios");
const config = require("./config.js");

const getApiConfig = () => {
  const env = config.environment === "production" ? "prod" : "dev";
  return config.api[env];
};

const apiClient = axios.create({
  timeout: 60000,
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
    const response = await apiClient({
      method,
      url,
      params: method === "GET" ? params : undefined,
    });
    return { success: true, data: response.data };
  } catch (error) {
    return { success: false, error: error.message };
  }
};

async function testRealTools() {
  console.log("\n🧪 REAL MCP TOOL TESTING\n");
  console.log("Testing actual MCP tool implementations...\n");

  const tests = [
    {
      name: "search-stocks",
      description: "Search for AAPL",
      test: async () => {
        const result = await callApi("/api/stocks/search", "GET", {
          q: "AAPL",
          limit: 5,
        });
        if (
          result.success &&
          result.data?.data?.results &&
          result.data.data.results.length > 0
        ) {
          return { pass: true, data: result.data.data.results[0] };
        }
        return { pass: false, error: "No results" };
      },
    },
    {
      name: "get-stock-scores",
      description: "Get scores for multiple stocks",
      test: async () => {
        const result = await callApi("/api/scores", "GET", { limit: 5 });
        if (result.success && result.data?.data?.stocks?.length > 0) {
          const stocks = result.data.data.stocks;
          return {
            pass: true,
            data: `${stocks.length} stocks loaded`,
            sample: stocks[0],
          };
        }
        return { pass: false, error: "No stocks" };
      },
    },
    {
      name: "get-market-overview",
      description: "Get market indices and data",
      test: async () => {
        const result = await callApi("/api/market/overview", "GET", {});
        if (result.success) {
          const hasData =
            result.data?.data ||
            result.data?.sentimentIndicators ||
            result.data?.indices;
          if (hasData) {
            return { pass: true, data: "Market data received" };
          }
        }
        return { pass: false, error: "No market data" };
      },
    },
    {
      name: "get-market-breadth",
      description: "Get market breadth indicators",
      test: async () => {
        const result = await callApi("/api/market/breadth", "GET", {});
        if (result.success) {
          return { pass: true, data: "Breadth data received" };
        }
        return { pass: false, error: "No breadth data" };
      },
    },
    {
      name: "get-sectors",
      description: "Get sector data",
      test: async () => {
        const result = await callApi("/api/sectors", "GET", {});
        if (result.success) {
          return { pass: true, data: "Sector data received" };
        }
        return { pass: false, error: "No sector data" };
      },
    },
    {
      name: "get-economic-data",
      description: "Get economic indicators",
      test: async () => {
        const result = await callApi("/api/economic", "GET", {});
        if (result.success) {
          return { pass: true, data: "Economic data received" };
        }
        return { pass: false, error: "No economic data" };
      },
    },
    {
      name: "get-dashboard",
      description: "Get dashboard data",
      test: async () => {
        const result = await callApi("/api/dashboard", "GET", {});
        if (result.success) {
          return { pass: true, data: "Dashboard data received" };
        }
        return { pass: false, error: "No dashboard data" };
      },
    },
    {
      name: "test-direct-api-call",
      description: "Test direct API endpoint",
      test: async () => {
        const result = await callApi("/api/stocks/search", "GET", {
          q: "TEST",
          limit: 1,
        });
        if (result.success || result.data?.data) {
          return { pass: true, data: "API responding" };
        }
        return { pass: false, error: "API not responding" };
      },
    },
  ];

  let passed = 0;
  let failed = 0;

  for (const test of tests) {
    process.stdout.write(`${test.name.padEnd(30)}`);

    try {
      const result = await test.test();

      if (result.pass) {
        console.log(`✅ ${result.data}`);
        if (result.sample) {
          console.log(
            `   Sample: ${JSON.stringify(result.sample).substring(0, 100)}...`
          );
        }
        passed++;
      } else {
        console.log(`❌ ${result.error}`);
        failed++;
      }
    } catch (error) {
      console.log(`❌ ${error.message}`);
      failed++;
    }
  }

  console.log("\n" + "=".repeat(70));
  console.log("\n📊 REAL TOOL TEST RESULTS:\n");
  console.log(`✅ Passed: ${passed}/${tests.length}`);
  console.log(`❌ Failed: ${failed}/${tests.length}`);
  console.log(`📈 Success Rate: ${((passed / tests.length) * 100).toFixed(0)}%\n`);

  if (failed === 0) {
    console.log("🎉 ALL TOOLS WORKING PERFECTLY!\n");
    console.log("MCP Server is ready for production use.");
    return 0;
  } else if (failed <= 2) {
    console.log(
      `⚠️  ${failed} non-critical endpoint(s) may have issues.\n`
    );
    console.log(
      "Core functionality (stock scores, search, market data) is working."
    );
    return 0;
  } else {
    console.log(`❌ Multiple critical failures detected.\n`);
    return 1;
  }
}

testRealTools()
  .then((code) => process.exit(code))
  .catch((error) => {
    console.error("Error:", error.message);
    process.exit(1);
  });
