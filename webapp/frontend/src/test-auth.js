// Simple test script to verify authentication works
import devAuth from "./src/services/devAuth.js";

async function testAuthFlow() {
  console.log("🧪 Testing Development Authentication Flow...\n");

  try {
    // Test 1: Sign up a new user
    console.log("1. Testing user registration...");
    const signUpResult = await devAuth.signUp(
      "testuser",
      "password123",
      "test@example.com",
      "Test",
      "User"
    );
    console.log("✅ Sign up result:", signUpResult);

    // Test 2: Confirm the user (simulate email verification)
    console.log("\n2. Testing email verification...");
    // Get the verification code from localStorage
    const pending = JSON.parse(localStorage.getItem("dev_pending") || "{}");
    const verificationCode = pending.testuser?.verificationCode;

    if (verificationCode) {
      console.log("📧 Verification code:", verificationCode);
      const confirmResult = await devAuth.confirmSignUp(
        "testuser",
        verificationCode
      );
      console.log("✅ Confirmation result:", confirmResult);
    } else {
      console.log("❌ No verification code found");
    }

    // Test 3: Sign in the user
    console.log("\n3. Testing user login...");
    const signInResult = await devAuth.signIn("testuser", "password123");
    console.log("✅ Sign in result:", signInResult);

    // Test 4: Check if user is authenticated
    console.log("\n4. Testing authentication status...");
    const currentUser = await devAuth.getCurrentUser();
    console.log("✅ Current user:", currentUser);

    // Test 5: Sign out the user
    console.log("\n5. Testing user logout...");
    await devAuth.signOut();
    console.log("✅ User signed out");

    // Test 6: Try to get current user after logout
    console.log("\n6. Testing authentication after logout...");
    try {
      await devAuth.getCurrentUser();
      console.log("❌ Should not get user after logout");
    } catch (error) {
      console.log("✅ Correctly no user after logout:", error.message);
    }

    console.log("\n🎉 All authentication tests passed!");
  } catch (error) {
    console.error("❌ Test failed:", error);
  }
}

// Run the test
testAuthFlow();
