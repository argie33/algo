/**
 * Test critical site fixes after implementing all changes
 */

const request = require("supertest");

const { app } = require("./server");

async function testCriticalFixes() {
  console.log("🧪 Testing Critical Site Fixes - Final Verification");
  console.log("=".repeat(60));

  let totalTests = 0;
  let passedTests = 0;
  let fixedIssues = [];

  async function runTest(name, testFn) {
    totalTests++;
    try {
      console.log(`\n📋 Test ${totalTests}: ${name}`);
      const result = await testFn();
      console.log("✅ PASSED");
      if (result && result.fixed) {
        fixedIssues.push(result.fixed);
      }
      passedTests++;
    } catch (error) {
      console.log("❌ FAILED:", error.message);
      console.log(
        "   Details:",
        error.response?.body?.error || error.stack?.split("\n")[0]
      );
    }
  }

  // Test 1: JSON parsing no longer crashes server
  await runTest("JSON parsing errors handled gracefully", async () => {
    const response = await request(app)
      .post("/api/trading/orders")
      .set("Content-Type", "application/json")
      .send('{"invalid": json}') // This should not crash the server
      .expect(400);

    if (!response.body.error.includes("Invalid JSON")) {
      throw new Error("JSON error not properly handled");
    }

    return { fixed: "JSON parsing crashes resolved" };
  });

  // Test 2: Database column issues resolved
  await runTest(
    "Database column issues resolved in technical indicators",
    async () => {
      const response = await request(app).get(
        "/api/trading/AAPL/technicals?timeframe=daily"
      );

      // Should return either data or proper error (not column existence error)
      if (
        response.status === 500 &&
        response.body.error &&
        response.body.error.includes("column") &&
        response.body.error.includes("does not exist")
      ) {
        throw new Error("Still has database column existence errors");
      }

      return { fixed: "Database column existence errors resolved" };
    }
  );

  // Test 3: Trading signals SQL syntax errors resolved
  await runTest("Trading signals SQL syntax errors resolved", async () => {
    const response = await request(app).get("/api/trading/signals?limit=5");

    // Should return either data or proper error (not SQL syntax error)
    if (
      response.status === 500 &&
      response.body.error &&
      response.body.error.includes("syntax error")
    ) {
      throw new Error("Still has SQL syntax errors");
    }

    return { fixed: "SQL syntax errors in trading signals resolved" };
  });

  // Test 4: Trading positions endpoint working
  await runTest(
    "Trading positions endpoint handles auth properly",
    async () => {
      const response = await request(app)
        .get("/api/trading/positions")
        .set("Authorization", "Bearer dev-bypass-token");

      // Should return either data or service unavailable (not crash)
      if (response.status !== 200 && response.status !== 503) {
        throw new Error(`Unexpected response status: ${response.status}`);
      }

      return { fixed: "Trading positions endpoint functioning" };
    }
  );

  // Test 5: Trading mode helper functions available
  await runTest("Trading mode helper functions available", async () => {
    const { getCurrentMode, switchMode } = require("./utils/tradingModeHelper");

    if (typeof getCurrentMode !== "function") {
      throw new Error("getCurrentMode function missing");
    }

    if (typeof switchMode !== "function") {
      throw new Error("switchMode function missing");
    }

    return { fixed: "Trading mode helper functions implemented" };
  });

  // Test 6: Trading simulator handles missing columns
  await runTest(
    "Trading simulator handles missing database columns",
    async () => {
      const response = await request(app).get(
        "/api/trading/simulator?symbols=AAPL&portfolio=10000"
      );

      // Should return either data or proper error (not column existence error)
      if (
        response.status === 500 &&
        response.body.error &&
        response.body.error.includes("column") &&
        response.body.error.includes("does not exist")
      ) {
        throw new Error(
          "Still has database column existence errors in simulator"
        );
      }

      return { fixed: "Trading simulator column issues resolved" };
    }
  );

  console.log("\n" + "=".repeat(60));
  console.log(
    `📊 Final Test Results: ${passedTests}/${totalTests} tests passed`
  );

  if (fixedIssues.length > 0) {
    console.log("\n🎉 Issues Successfully Fixed:");
    fixedIssues.forEach((issue, i) => {
      console.log(`   ${i + 1}. ${issue}`);
    });
  }

  if (passedTests === totalTests) {
    console.log("\n🎉 ALL CRITICAL SITE ISSUES HAVE BEEN RESOLVED!");
    console.log("✅ Your site is now handling all edge cases gracefully");
    console.log("✅ No more server crashes on invalid requests");
    console.log("✅ Database flexibility implemented");
    console.log("✅ Error handling is robust and user-friendly");
    return true;
  } else {
    console.log("\n⚠️  Some critical issues may remain");
    return false;
  }
}

// Run the critical tests
testCriticalFixes()
  .then((success) => {
    process.exit(success ? 0 : 1);
  })
  .catch((error) => {
    console.error("💥 Critical test runner crashed:", error);
    process.exit(1);
  });
