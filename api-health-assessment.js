#!/usr/bin/env node

const axios = require("axios");

const API_BASE = "https://ye9syrnj8c.execute-api.us-east-1.amazonaws.com/dev";

// Health assessment test suite
async function assessAPIHealth() {
  console.log("🏥 API Health Assessment Started\n");
  console.log(`🎯 Testing against: ${API_BASE}\n`);

  const results = {
    healthy: [],
    degraded: [],
    broken: [],
    missing: [],
  };

  // Core health endpoints
  const healthEndpoints = [
    {
      name: "Quick Health Check",
      url: "/api/health?quick=true",
      expected: 200,
    },
    { name: "Full Health Check", url: "/api/health", expected: 200 },
    { name: "Database Health", url: "/api/health/database", expected: 200 },
    {
      name: "Database Diagnostics",
      url: "/api/health/database/diagnostics",
      expected: 200,
    },
    { name: "WebSocket Health", url: "/api/websocket/health", expected: 200 },
  ];

  // Stock endpoints
  const stockEndpoints = [
    { name: "Stock Sectors", url: "/api/stocks/sectors", expected: 200 },
    {
      name: "Stock Public Sample",
      url: "/api/stocks/public/sample",
      expected: 200,
    },
    { name: "Stock Detail (AAPL)", url: "/api/stocks/AAPL", expected: 200 },
    { name: "Stock Search", url: "/api/stocks/search?q=AAPL", expected: 200 },
  ];

  // Portfolio endpoints (require auth)
  const portfolioEndpoints = [
    {
      name: "Portfolio Analytics",
      url: "/api/portfolio/analytics",
      expected: 401,
    }, // Should return 401 without auth
    {
      name: "Portfolio Holdings",
      url: "/api/portfolio/holdings",
      expected: 401,
    },
  ];

  // Combined test suite
  const allTests = [
    ...healthEndpoints,
    ...stockEndpoints,
    ...portfolioEndpoints,
  ];

  console.log(`🧪 Testing ${allTests.length} endpoints...\n`);

  for (const test of allTests) {
    try {
      const startTime = Date.now();
      const response = await axios.get(`${API_BASE}${test.url}`, {
        timeout: 10000,
        validateStatus: (status) => status < 500, // Don't throw on 4xx errors
      });
      const duration = Date.now() - startTime;

      const status = response.status;
      const isHealthy = status === test.expected;
      const isDegraded = status === 200 && test.expected === 401; // Unexpected success
      const isBroken = status >= 500;

      if (isHealthy) {
        results.healthy.push({
          name: test.name,
          url: test.url,
          status,
          duration,
          data: response.data,
        });
        console.log(`✅ ${test.name} - ${status} (${duration}ms)`);
      } else if (isDegraded) {
        results.degraded.push({
          name: test.name,
          url: test.url,
          status,
          duration,
          issue: "Authentication bypassed unexpectedly",
        });
        console.log(
          `⚠️  ${test.name} - ${status} (${duration}ms) - Auth bypassed`
        );
      } else if (isBroken) {
        results.broken.push({
          name: test.name,
          url: test.url,
          status,
          duration,
          error: response.data?.error || "Server error",
        });
        console.log(
          `❌ ${test.name} - ${status} (${duration}ms) - ${response.data?.error || "Server error"}`
        );
      } else {
        results.broken.push({
          name: test.name,
          url: test.url,
          status,
          duration,
          error: `Unexpected status: ${status}, expected: ${test.expected}`,
        });
        console.log(
          `❌ ${test.name} - ${status} (${duration}ms) - Unexpected status`
        );
      }
    } catch (error) {
      if (error.code === "ECONNABORTED") {
        results.broken.push({
          name: test.name,
          url: test.url,
          error: "Timeout after 10 seconds",
        });
        console.log(`⏱️  ${test.name} - TIMEOUT`);
      } else if (error.response) {
        const status = error.response.status;
        if (status === test.expected) {
          results.healthy.push({
            name: test.name,
            url: test.url,
            status,
            error: error.response.data?.error || "Expected error",
          });
          console.log(`✅ ${test.name} - ${status} (Expected)`);
        } else {
          results.broken.push({
            name: test.name,
            url: test.url,
            status,
            error: error.response.data?.error || error.message,
          });
          console.log(
            `❌ ${test.name} - ${status} - ${error.response.data?.error || error.message}`
          );
        }
      } else {
        results.missing.push({
          name: test.name,
          url: test.url,
          error: error.message,
        });
        console.log(`🔴 ${test.name} - CONNECTION_ERROR - ${error.message}`);
      }
    }
  }

  console.log("\n📊 HEALTH ASSESSMENT SUMMARY\n");
  console.log(`✅ Healthy endpoints: ${results.healthy.length}`);
  console.log(`⚠️  Degraded endpoints: ${results.degraded.length}`);
  console.log(`❌ Broken endpoints: ${results.broken.length}`);
  console.log(`🔴 Missing endpoints: ${results.missing.length}`);

  // Detailed breakdown
  if (results.broken.length > 0) {
    console.log("\n🚨 BROKEN ENDPOINTS:");
    results.broken.forEach((endpoint) => {
      console.log(`  - ${endpoint.name}: ${endpoint.error}`);
    });
  }

  if (results.degraded.length > 0) {
    console.log("\n⚠️  DEGRADED ENDPOINTS:");
    results.degraded.forEach((endpoint) => {
      console.log(`  - ${endpoint.name}: ${endpoint.issue}`);
    });
  }

  if (results.missing.length > 0) {
    console.log("\n🔴 MISSING ENDPOINTS:");
    results.missing.forEach((endpoint) => {
      console.log(`  - ${endpoint.name}: ${endpoint.error}`);
    });
  }

  // Check specific data issues
  console.log("\n🔍 DATA QUALITY CHECKS:");

  const healthyHealthCheck = results.healthy.find(
    (r) => r.name === "Full Health Check"
  );
  if (healthyHealthCheck) {
    const data = healthyHealthCheck.data;
    if (data.database?.status === "connected") {
      console.log("✅ Database connection: OK");
    } else {
      console.log("❌ Database connection: FAILED");
    }
  }

  const stockSectors = results.healthy.find((r) => r.name === "Stock Sectors");
  if (stockSectors) {
    const data = stockSectors.data;
    if (data.data && data.data.length > 0) {
      console.log(`✅ Stock sectors: ${data.data.length} sectors available`);
    } else {
      console.log("❌ Stock sectors: No data available");
    }
  }

  const stockSample = results.healthy.find(
    (r) => r.name === "Stock Public Sample"
  );
  if (stockSample) {
    const data = stockSample.data;
    if (data.data && data.data.length > 0) {
      console.log(`✅ Stock sample data: ${data.data.length} stocks available`);
    } else {
      console.log("❌ Stock sample data: No data available");
    }
  }

  // Overall health score
  const totalEndpoints = allTests.length;
  const healthyCount = results.healthy.length;
  const healthScore = Math.round((healthyCount / totalEndpoints) * 100);

  console.log(`\n🎯 OVERALL HEALTH SCORE: ${healthScore}%`);

  if (healthScore >= 90) {
    console.log("🟢 System Status: HEALTHY");
  } else if (healthScore >= 70) {
    console.log("🟡 System Status: DEGRADED");
  } else {
    console.log("🔴 System Status: CRITICAL");
  }

  return results;
}

// Run the assessment
assessAPIHealth().catch(console.error);
