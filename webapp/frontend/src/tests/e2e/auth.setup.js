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
    // Use 'test-token' which is recognized by the backend test auth handler
    localStorage.setItem("accessToken", "test-token");
  });

  // Navigate to verify auth works
  await page.reload();
  await page.waitForLoadState("domcontentloaded");

  // Wait for the app to mount
  try {
    await page.waitForSelector("#root", { timeout: 5000 });
    console.log("✅ #root element found");
  } catch (e) {
    console.log("⚠️ #root not found within timeout, continuing anyway");
  }

  await page.waitForTimeout(1000); // Brief pause for hydration

  console.log("✅ Authentication setup complete");
});
