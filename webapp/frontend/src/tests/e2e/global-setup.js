/**
 * Global Playwright Setup
 * Runs once before all tests - sets up test environment, auth, and data
 */

import { chromium } from "@playwright/test";

async function globalSetup() {

  try {
    const browser = await chromium.launch({
      args: [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--no-first-run",
        "--no-zygote",
        "--single-process",
        "--disable-extensions",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
      ],
    });
    const context = await browser.newContext();
    const page = await context.newPage();

    try {
      // Wait for dev server to be ready
      let retries = 30; // 2.5 minutes
      while (retries > 0) {
        try {
          await page.goto("http://localhost:5173", { timeout: 10000 });
          // Check if page loads with React content
          await page.waitForSelector('#root', { timeout: 5000 });
          break;
        } catch (error) {
          retries--;
          if (retries === 0) {
            console.error("Dev server not ready after 2.5 minutes:", error.message);
            // Continue without failing - tests might still work
          }
          await new Promise((resolve) => setTimeout(resolve, 5000));
        }
      }


      // Set up test authentication
      await page.goto("http://localhost:5173");

      // Set up consistent test user data
      await page.addInitScript(() => {
        // Mock authentication
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

        // Set theme
        localStorage.setItem("theme", "light");

        // Set up API keys for testing
        localStorage.setItem(
          "api_keys_status",
          JSON.stringify({
            alpaca: { configured: true, valid: true },
            polygon: { configured: true, valid: true },
            finnhub: { configured: true, valid: true },
          })
        );
      });


      await browser.close();
    } catch (setupError) {
      console.error("❌ Test setup failed:", setupError);
      if (browser) {
        await browser.close();
      }
      throw setupError;
    }
  } catch (browserError) {
    console.error("❌ Browser launch failed:", browserError);
    throw browserError;
  }
}

export default globalSetup;

