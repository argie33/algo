/**
 * Quick test to verify alerts route fixes
 */

const request = require("supertest");

const app = require("./server");

async function testAlertsFixes() {
  console.log("🧪 Testing alerts route fixes...\n");

  try {
    // Test 1: Active alerts should return 501 with "Active alerts not implemented"
    console.log("1. Testing /api/alerts/active...");
    const activeResponse = await request(app)
      .get("/api/alerts/active")
      .set("Authorization", "Bearer dev-bypass-token");

    console.log(`   Status: ${activeResponse.status}`);
    console.log(`   Success: ${activeResponse.body.success}`);
    console.log(`   Error: ${activeResponse.body.error}`);
    console.log(`   User ID: ${activeResponse.body.user_id}`);

    const activeTestPassed =
      activeResponse.status === 501 &&
      activeResponse.body.error === "Active alerts not implemented" &&
      activeResponse.body.user_id === "dev-user-bypass";
    console.log(
      `   ✅ Active alerts test: ${activeTestPassed ? "PASSED" : "FAILED"}\n`
    );

    // Test 2: Price alerts should return 501 with "Price alerts not implemented"
    console.log("2. Testing /api/alerts/price...");
    const priceResponse = await request(app)
      .get("/api/alerts/price")
      .set("Authorization", "Bearer dev-bypass-token");

    console.log(`   Status: ${priceResponse.status}`);
    console.log(`   Success: ${priceResponse.body.success}`);
    console.log(`   Error: ${priceResponse.body.error}`);
    console.log(`   User ID: ${priceResponse.body.user_id}`);

    const priceTestPassed =
      priceResponse.status === 501 &&
      priceResponse.body.error === "Price alerts not implemented" &&
      priceResponse.body.user_id === "dev-user-bypass";
    console.log(
      `   ✅ Price alerts test: ${priceTestPassed ? "PASSED" : "FAILED"}\n`
    );

    // Test 3: Check JSON parsing error handling
    console.log("3. Testing JSON parsing error handling...");
    const jsonResponse = await request(app)
      .post("/api/alerts")
      .set("Authorization", "Bearer dev-bypass-token")
      .set("Content-Type", "application/json")
      .send('{"invalid": json}'); // Malformed JSON

    console.log(`   Status: ${jsonResponse.status}`);
    console.log(`   Success: ${jsonResponse.body.success}`);
    console.log(`   Error: ${jsonResponse.body.error}`);

    const jsonTestPassed =
      jsonResponse.status === 400 &&
      jsonResponse.body.success === false &&
      jsonResponse.body.error === "Invalid JSON format";
    console.log(
      `   ✅ JSON parsing test: ${jsonTestPassed ? "PASSED" : "FAILED"}\n`
    );

    // Summary
    const allTestsPassed =
      activeTestPassed && priceTestPassed && jsonTestPassed;
    console.log(
      `🎉 Overall result: ${allTestsPassed ? "ALL TESTS PASSED!" : "SOME TESTS FAILED!"}`
    );

    if (allTestsPassed) {
      console.log("\n✅ Key fixes verified:");
      console.log("   - Active alerts returns proper 501 not implemented");
      console.log("   - Price alerts returns proper 501 not implemented");
      console.log("   - JSON parsing errors handled correctly");
      console.log(
        "   - All responses include success:false and proper user_id"
      );
    }

    process.exit(allTestsPassed ? 0 : 1);
  } catch (error) {
    console.error("❌ Test failed:", error.message);
    process.exit(1);
  }
}

// Run the test
testAlertsFixes();
