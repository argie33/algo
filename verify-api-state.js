#!/usr/bin/env node
/**
 * API State Verification Tool
 * Tests all critical endpoints to identify data availability and response format issues
 */

const http = require("http");
const https = require("https");

// Configuration
const API_BASE = process.env.API_URL || "http://localhost:3000";
const ENDPOINTS = [
  // Core stock data
  { method: "GET", path: "/api/stocks", name: "Stocks List" },
  { method: "GET", path: "/api/stocks/search?q=AAPL", name: "Stock Search" },
  { method: "GET", path: "/api/stocks/deep-value?limit=5", name: "Deep Value Stocks" },

  // Earnings data
  { method: "GET", path: "/api/earnings/calendar?symbol=AAPL", name: "Earnings Calendar" },
  { method: "GET", path: "/api/earnings/data?symbol=AAPL", name: "Earnings Data" },

  // Scores
  { method: "GET", path: "/api/scores/stockscores?limit=5", name: "Stock Scores" },

  // Market
  { method: "GET", path: "/api/market/status", name: "Market Status" },

  // Sectors
  { method: "GET", path: "/api/sectors", name: "Sectors" },

  // Technicals
  { method: "GET", path: "/api/technicals/macd?symbol=AAPL", name: "Technical Indicators" },
];

function makeRequest(url) {
  return new Promise((resolve, reject) => {
    const protocol = url.startsWith("https") ? https : http;

    const req = protocol.get(url, { timeout: 5000 }, (res) => {
      let data = "";

      res.on("data", (chunk) => {
        data += chunk;
      });

      res.on("end", () => {
        try {
          const parsed = JSON.parse(data);
          resolve({
            status: res.statusCode,
            data: parsed,
            size: data.length,
            headers: res.headers,
          });
        } catch (e) {
          resolve({
            status: res.statusCode,
            data: null,
            rawData: data.substring(0, 200),
            error: "JSON parse error",
            size: data.length,
          });
        }
      });
    });

    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timeout"));
    });

    req.on("error", reject);
  });
}

async function testEndpoint(endpoint) {
  const url = `${API_BASE}${endpoint.path}`;
  console.log(`\n📍 Testing: ${endpoint.name}`);
  console.log(`   URL: ${url}`);

  try {
    const result = await makeRequest(url);

    console.log(`   ✅ Status: ${result.status}`);
    console.log(`   📦 Response Size: ${result.size} bytes`);

    // Check response structure
    if (result.data) {
      const hasSuccess = result.data.success !== undefined;
      const hasData = result.data.data !== undefined;
      const hasItems = result.data.items !== undefined;
      const hasPagination = result.data.pagination !== undefined;

      console.log(`   📋 Structure:`);
      console.log(`      success: ${hasSuccess ? "✅" : "❌"}`);
      console.log(`      data: ${hasData ? "✅" : "❌"}`);
      console.log(`      items: ${hasItems ? "✅" : "❌"}`);
      console.log(`      pagination: ${hasPagination ? "✅" : "❌"}`);

      // Count items in data
      if (hasData && result.data.data) {
        const dataKeys = Object.keys(result.data.data);
        if (Array.isArray(result.data.data)) {
          console.log(`      Data items: ${result.data.data.length}`);
        } else {
          console.log(`      Data keys: ${dataKeys.length} (${dataKeys.slice(0, 3).join(", ")}...)`);
        }
      }

      if (hasItems && result.data.items) {
        console.log(`      Items count: ${result.data.items.length}`);
      }
    } else {
      console.log(`   ❌ Could not parse response data`);
      if (result.rawData) {
        console.log(`   Raw: ${result.rawData}`);
      }
    }
  } catch (error) {
    console.log(`   ❌ Error: ${error.message}`);
  }
}

async function runTests() {
  console.log("🚀 API State Verification");
  console.log(`   Base URL: ${API_BASE}`);
  console.log(`   Testing ${ENDPOINTS.length} endpoints...\n`);

  for (const endpoint of ENDPOINTS) {
    await testEndpoint(endpoint);
  }

  console.log("\n\n📊 Summary:");
  console.log("   Check the results above to identify which endpoints have data");
  console.log("   and which response formats are being used.");
}

runTests().catch(console.error);
