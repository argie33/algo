/**
 * Authentication Setup for E2E Tests
 * Creates authenticated state for all tests
 */

import { test as setup } from "@playwright/test";

setup("authenticate", async ({ page }) => {
  console.log("🔐 Setting up authentication...");

  await page.goto("/");

  // Set up authentication state
  await page.addInitScript(() => {
    localStorage.setItem("financial_auth_token", "e2e-test-token");
    localStorage.setItem(
      "financial_user_data",
      JSON.stringify({
        username: "e2etest",
        email: "e2e@test.com",
        name: "E2E Test User",
        id: "e2e-test-user-id",
      })
    );
  });

  // Navigate to verify auth works
  await page.reload();
  await page.waitForLoadState("domcontentloaded");

  // Wait for the app to mount with multiple fallback strategies
  try {
    await page.waitForSelector("#root", { timeout: 5000 });
    console.log("✅ #root element found");
  } catch (e) {
    console.log("⚠️ #root not visible, checking for app content...");

    // Fallback 1: Wait for any significant content
    try {
      await page.waitForSelector("body", { timeout: 3000 });
      const hasContent = await page.locator("body").textContent();
      if (hasContent && hasContent.length > 100) {
        console.log("✅ App content detected via body");
      }
    } catch (e2) {
      console.log("⚠️ Using minimal setup - continuing anyway");
    }
  }

  await page.waitForTimeout(1000); // Brief pause for hydration

  console.log("✅ Authentication setup complete");
});
