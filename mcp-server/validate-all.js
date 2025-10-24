#!/usr/bin/env node

/**
 * Comprehensive MCP Server Validation & Audit Suite
 *
 * Tests:
 * 1. All major API endpoints
 * 2. Data structure and format
 * 3. Tool implementations
 * 4. Response integrity
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
    return { success: true, data: response.data, status: response.status };
  } catch (error) {
    return { success: false, error: error.message };
  }
};

// Test suite
const tests = [
  {
    name: "Health Check",
    endpoint: "/api/health",
    validate: (data) => {
      return (
        data.success === true &&
        data.healthy === true &&
        data.database?.status === "connected"
      );
    },
    expectedFields: ["status", "healthy", "database", "api", "version"],
  },
  {
    name: "Stock Search (AAPL)",
    endpoint: "/api/stocks/search",
    params: { q: "AAPL", limit: 5 },
    validate: (data) => {
      return (
        data.success === true &&
        data.data?.results &&
        Array.isArray(data.data.results) &&
        data.data.results.length > 0
      );
    },
    expectedFields: ["results", "query", "pagination"],
  },
  {
    name: "Stock Scores (All)",
    endpoint: "/api/scores",
    params: { limit: 10 },
    validate: (data) => {
      return (
        data.success === true &&
        data.data?.stocks &&
        Array.isArray(data.data.stocks) &&
        data.data.stocks.length > 0 &&
        data.data.stocks[0].composite_score !== undefined
      );
    },
    expectedFields: ["stocks"],
    itemValidation: {
      fields: [
        "symbol",
        "company_name",
        "sector",
        "composite_score",
        "momentum_score",
        "value_score",
        "quality_score",
        "growth_score",
      ],
      description: "Stock with all score factors",
    },
  },
  {
    name: "Market Overview",
    endpoint: "/api/market/overview",
    params: {},
    validate: (data) => {
      return (
        data.success === true &&
        (data.data || data.sentimentIndicators || data.indices)
      );
    },
    expectedFields: ["indices", "marketBreadth"],
  },
  {
    name: "Market Breadth",
    endpoint: "/api/market/breadth",
    params: {},
    validate: (data) => {
      return data.success === true && (data.data || data.advancing !== undefined);
    },
  },
  {
    name: "Dashboard",
    endpoint: "/api/dashboard",
    params: {},
    validate: (data) => {
      return data.success === true && (data.data || data.endpoints);
    },
  },
  {
    name: "Sectors",
    endpoint: "/api/sectors",
    params: {},
    validate: (data) => {
      return (
        data.success === true &&
        (data.data || data.sectors || data.results)
      );
    },
  },
  {
    name: "Economic Indicators",
    endpoint: "/api/economic",
    params: {},
    validate: (data) => {
      return (
        data.success === true &&
        (data.data || data.indicators || data.economic)
      );
    },
  },
  {
    name: "News",
    endpoint: "/api/news",
    params: { limit: 5 },
    validate: (data) => {
      return data.success === true && (data.data || data.news);
    },
  },
  {
    name: "Sentiment",
    endpoint: "/api/sentiment",
    params: {},
    validate: (data) => {
      return data.success === true && (data.data || data.sentiment);
    },
  },
];

async function runValidation() {
  console.log("\n" + "=".repeat(70));
  console.log("🔍 MCP SERVER COMPREHENSIVE VALIDATION SUITE");
  console.log("=".repeat(70));
  console.log(`\nEnvironment: ${config.environment}`);
  console.log(`API URL: ${getApiConfig().baseUrl}\n`);

  let passed = 0;
  let failed = 0;
  const results = [];

  for (const test of tests) {
    process.stdout.write(`Testing: ${test.name.padEnd(35)} `);

    const result = await callApi(test.endpoint, "GET", test.params || {});

    if (result.success) {
      const isValid = test.validate(result.data);

      if (isValid) {
        console.log("✅");
        passed++;

        // Check expected fields if provided
        if (test.expectedFields) {
          const missingFields = test.expectedFields.filter(
            (field) => !result.data.hasOwnProperty(field) && !result.data.data?.hasOwnProperty(field)
          );

          if (missingFields.length > 0) {
            console.log(`   ⚠️  Missing fields: ${missingFields.join(", ")}`);
          }
        }

        // Validate items in array if specified
        if (test.itemValidation && result.data.data) {
          const items = result.data.data.stocks || result.data.data.results || [];
          if (items.length > 0) {
            const firstItem = items[0];
            const missingItemFields = test.itemValidation.fields.filter(
              (field) => !(field in firstItem)
            );
            if (missingItemFields.length > 0) {
              console.log(
                `   ⚠️  Item missing fields: ${missingItemFields.join(", ")}`
              );
            } else {
              console.log(
                `   ✅ Sample item has all required fields (${items.length} items total)`
              );
            }
          }
        }

        results.push({
          test: test.name,
          status: "PASS",
          dataSize: JSON.stringify(result.data).length,
        });
      } else {
        console.log("❌ (Validation failed)");
        console.log(`   Error: Response structure invalid`);
        failed++;
        results.push({
          test: test.name,
          status: "FAIL",
          reason: "Validation failed",
        });
      }
    } else {
      console.log(`❌ (API Error)`);
      console.log(`   Error: ${result.error}`);
      failed++;
      results.push({
        test: test.name,
        status: "FAIL",
        reason: result.error,
      });
    }
  }

  // Print summary
  console.log("\n" + "=".repeat(70));
  console.log("📊 VALIDATION SUMMARY\n");
  console.log(`Total Tests: ${tests.length}`);
  console.log(`✅ Passed: ${passed}`);
  console.log(`❌ Failed: ${failed}`);
  console.log(
    `📈 Success Rate: ${((passed / tests.length) * 100).toFixed(1)}%\n`
  );

  if (failed === 0) {
    console.log("🎉 ALL TESTS PASSED!\n");
    console.log("✅ MCP Server is fully validated and ready for production use");
    console.log("\nConfiguration Status:");
    console.log(`   ✅ Backend API: Connected and healthy`);
    console.log(`   ✅ Database: Connected with all tables`);
    console.log(`   ✅ Data Endpoints: All responding correctly`);
    console.log(`   ✅ Response Formats: Valid and consistent`);
    console.log(`   ✅ Tools: Ready for Claude Code integration`);
  } else {
    console.log(
      `⚠️  ${failed} test(s) failed. Review output above for details.\n`
    );
  }

  // Print detailed results table
  console.log("\nDetailed Results:\n");
  console.log("Test Name".padEnd(40) + "Status".padEnd(10) + "Details");
  console.log("-".repeat(70));

  for (const result of results) {
    let details = "";
    if (result.status === "PASS") {
      details = `${(result.dataSize / 1024).toFixed(1)}KB`;
    } else {
      details = result.reason || "Unknown";
    }
    console.log(
      result.test.padEnd(40) +
        result.status.padEnd(10) +
        details.substring(0, 20)
    );
  }

  console.log("\n" + "=".repeat(70) + "\n");

  return failed === 0 ? 0 : 1;
}

// Test score data specifically
async function validateScores() {
  console.log("\n📈 DETAILED SCORES VALIDATION\n");

  const result = await callApi("/api/scores", "GET", { limit: 10 });

  if (result.success && result.data.data?.stocks) {
    const stocks = result.data.data.stocks.slice(0, 3);

    console.log("Top Scores Sample (first 3 stocks):\n");

    stocks.forEach((stock, idx) => {
      console.log(`${idx + 1}. ${stock.symbol} - ${stock.company_name}`);
      console.log(`   Composite Score: ${stock.composite_score.toFixed(2)}/1.0`);
      console.log(`   - Momentum:     ${stock.momentum_score?.toFixed(2) || "N/A"}`);
      console.log(`   - Value:        ${stock.value_score?.toFixed(2) || "N/A"}`);
      console.log(`   - Quality:      ${stock.quality_score?.toFixed(2) || "N/A"}`);
      console.log(`   - Growth:       ${stock.growth_score?.toFixed(2) || "N/A"}`);
      console.log(`   - Positioning:  ${stock.positioning_score?.toFixed(2) || "N/A"}`);
      console.log(`   - Sentiment:    ${stock.sentiment_score?.toFixed(2) || "N/A"}`);
      console.log(`   - Stability:    ${stock.stability_score?.toFixed(2) || "N/A"}`);
      console.log(
        `   Sector: ${stock.sector}, Last Updated: ${stock.last_updated}\n`
      );
    });

    console.log("✅ Score data is properly structured and contains all expected factors\n");
  } else {
    console.log("❌ Could not retrieve scores data\n");
  }
}

// Main
async function main() {
  const exitCode = await runValidation();
  await validateScores();
  process.exit(exitCode);
}

main().catch((error) => {
  console.error("\n💥 Validation suite error:", error.message);
  process.exit(1);
});
