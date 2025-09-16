import { test, expect } from "@playwright/test";

test("Test sentiment page specifically for MUI Tabs error", async ({
  page,
}) => {
  // Monitor console errors
  const consoleErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });

  // Set up auth like in the main tests
  await page.addInitScript(() => {
    localStorage.setItem("financial_auth_token", "e2e-test-token");
    localStorage.setItem(
      "api_keys_status",
      JSON.stringify({
        alpaca: { configured: true, valid: true },
        polygon: { configured: true, valid: true },
        finnhub: { configured: true, valid: true },
      })
    );
  });

  console.log("🧪 Testing sentiment page specifically...");

  // Navigate directly to sentiment page
  await page.goto("/sentiment", {
    waitUntil: "domcontentloaded",
    timeout: 15000,
  });
  await page.waitForSelector("#root", { state: "attached", timeout: 10000 });
  await page.waitForTimeout(3000);

  // Check for MUI Tabs errors specifically
  const muiTabsErrors = consoleErrors.filter(
    (error) =>
      error.includes("MUI:") &&
      error.includes("Tabs") &&
      error.includes("value")
  );

  console.log(`📊 Total console errors: ${consoleErrors.length}`);
  console.log(`🎯 MUI Tabs errors: ${muiTabsErrors.length}`);

  if (muiTabsErrors.length > 0) {
    console.log(`❌ MUI Tabs errors found:`);
    muiTabsErrors.forEach((error) => console.log(`   - ${error}`));
  } else {
    console.log(`✅ No MUI Tabs errors on sentiment page`);
  }

  if (consoleErrors.length > 0) {
    console.log(`📝 All console errors:`);
    consoleErrors
      .slice(0, 5)
      .forEach((error) => console.log(`   - ${error.slice(0, 100)}...`));
  }

  // Should not have MUI Tabs errors on individual page
  expect(muiTabsErrors.length).toBe(0);
});
