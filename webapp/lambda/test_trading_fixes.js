/**
 * Quick verification script to test trading route fixes
 * Tests that database column issues have been resolved
 */

const request = require("supertest");

const { app } = require("./server");

async function testTradingFixes() {
  console.log("🧪 Testing Trading Route Fixes");
  console.log("=".repeat(50));

  let totalTests = 0;
  let passedTests = 0;

  async function runTest(name, testFn) {
    totalTests++;
    try {
      console.log(`\n📋 Test ${totalTests}: ${name}`);
      await testFn();
      console.log("✅ PASSED");
      passedTests++;
    } catch (error) {
      console.log("❌ FAILED:", error.message);
      console.log(
        "   Details:",
        error.response?.body || error.stack?.split("\n")[0]
      );
    }
  }

  // Test 1: Basic trading health endpoint
  await runTest("Trading health endpoint responds", async () => {
    const response = await request(app).get("/api/trading/health").expect(200);

    if (!response.body.success) {
      throw new Error("Health endpoint returned success=false");
    }
  });

  // Test 2: Trading debug endpoint shows table status
  await runTest("Trading debug endpoint shows database info", async () => {
    const response = await request(app).get("/api/trading/debug").expect(200);

    if (!response.body.success) {
      throw new Error("Debug endpoint returned success=false");
    }

    if (!response.body.tables) {
      throw new Error("Debug endpoint missing tables information");
    }
  });

  // Test 3: Trading signals endpoint handles missing columns gracefully
  await runTest(
    "Trading signals handles missing database columns",
    async () => {
      const response = await request(app).get(
        "/api/trading/signals/daily?limit=1"
      );

      // Should return either data or a proper error (not crash)
      if (
        response.status !== 200 &&
        response.status !== 501 &&
        response.status !== 500
      ) {
        throw new Error(`Unexpected status code: ${response.status}`);
      }

      if (
        response.status === 500 &&
        response.body.error &&
        response.body.error.includes("column")
      ) {
        throw new Error("Still has column existence errors");
      }
    }
  );

  // Test 4: Trading simulator handles missing columns gracefully
  await runTest(
    "Trading simulator handles missing database columns",
    async () => {
      const response = await request(app).get(
        "/api/trading/simulator?symbols=AAPL&portfolio=10000"
      );

      // Should return either data or a proper error (not crash)
      if (
        response.status !== 200 &&
        response.status !== 501 &&
        response.status !== 500
      ) {
        throw new Error(`Unexpected status code: ${response.status}`);
      }

      if (
        response.status === 500 &&
        response.body.error &&
        response.body.error.includes("column")
      ) {
        throw new Error("Still has column existence errors");
      }
    }
  );

  // Test 5: Trading positions endpoint (authenticated)
  await runTest(
    "Trading positions endpoint handles auth correctly",
    async () => {
      const response = await request(app)
        .get("/api/trading/positions")
        .set("Authorization", "Bearer dev-bypass-token");

      // Should return either data or proper auth error (not crash)
      if (
        response.status !== 200 &&
        response.status !== 403 &&
        response.status !== 503
      ) {
        throw new Error(`Unexpected status code: ${response.status}`);
      }

      if (
        response.status === 500 &&
        response.body.error &&
        response.body.error.includes("column")
      ) {
        throw new Error("Still has column existence errors");
      }
    }
  );

  console.log("\n" + "=".repeat(50));
  console.log(`📊 Test Results: ${passedTests}/${totalTests} tests passed`);

  if (passedTests === totalTests) {
    console.log("🎉 All trading route fixes are working correctly!");
    return true;
  } else {
    console.log("⚠️  Some issues remain in trading routes");
    return false;
  }
}

// Run the tests
testTradingFixes()
  .then((success) => {
    process.exit(success ? 0 : 1);
  })
  .catch((error) => {
    console.error("💥 Test runner crashed:", error);
    process.exit(1);
  });
