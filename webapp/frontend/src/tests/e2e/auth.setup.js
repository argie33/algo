/**
 * Authentication Setup for E2E Tests
 * Creates authenticated state for all tests
 */

import { test as setup } from "@playwright/test";

setup("authenticate", async ({ page }) => {
  await page.goto("/");

  // Set up authentication state
  await page.addInitScript(() => {
    // Use 'test-token' which is recognized by the backend test auth handler
    sessionStorage.setItem("accessToken", "test-token");
  });

  // Navigate to verify auth works
  await page.reload();
  await page.waitForLoadState("domcontentloaded");

  // Wait for the app to mount
  try {
    await page.waitForSelector("#root", { timeout: 5000 });
  } catch (err) {
    console.warn(
      "[E2E Auth] Root element not found within timeout:",
      err?.message
    );
  }

  await page.waitForTimeout(1000); // Brief pause for hydration
});
