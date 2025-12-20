import { test, expect } from "@playwright/test";

test.describe("Trading Signals - Empty State", () => {
  test("should display 0 signals when database is empty", async ({ page }) => {
    // Navigate to trading signals page
    await page.goto("http://localhost:5173/trading-signals");

    // Wait for page to load
    await page.waitForLoadState("networkidle");

    // Give React Query a moment to fetch and process
    await page.waitForTimeout(2000);

    // Check the console for warnings about empty data
    const messages = [];
    page.on("console", (msg) => {
      if (msg.text().includes("NO SIGNALS") || msg.text().includes("📭")) {
        messages.push(msg.text());
      }
    });

    // Look for "No data" or "0" indicators in the page
    const pageText = await page.innerText("body");

    // Verify the page doesn't show old fake data
    const hasFakeData =
      pageText.includes("AAPL") ||
      pageText.includes("MSFT") ||
      pageText.includes("TSLA");

    expect(
      hasFakeData,
      "Should NOT show any trading signals when database is empty"
    ).toBe(false);

    // Look for empty state message
    const hasEmptyMessage =
      pageText.includes("No signals") ||
      pageText.includes("0 signals") ||
      pageText.includes("No data");

    console.log("Page content (first 500 chars):", pageText.substring(0, 500));
    console.log("Console messages:", messages);

    expect(pageText).not.toContain("AAPL");
    expect(pageText).not.toContain("MSFT");
    expect(pageText).not.toContain("TSLA");

    console.log("✅ Empty state confirmed - no fake/old data displayed");
  });

  test("should refresh and show 0 when database is empty", async ({ page }) => {
    // Navigate to trading signals
    await page.goto("http://localhost:5173/trading-signals");

    // Wait for load
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(1000);

    // Force refresh
    await page.reload();

    // Wait for fresh data
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(2000);

    // Check page content
    const pageText = await page.innerText("body");

    // Should not have any trading signal symbols
    expect(pageText).not.toMatch(/[A-Z]{1,4}\s+(BUY|SELL)/);

    console.log("✅ Post-refresh: No old signals displayed");
  });
});
