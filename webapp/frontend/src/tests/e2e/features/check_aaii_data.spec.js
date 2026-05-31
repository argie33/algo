import { test, expect } from "@playwright/test";

test.describe("Check AAII Data", () => {
  test("should log AAII data to the console", async ({ page }) => {
    const consoleLogs = [];
    page.on("console", (msg) => {
      consoleLogs.push(msg.text());
    });

    await page.goto("/market", {
      waitUntil: "domcontentloaded",
      timeout: 15000,
    });

    await page.waitForSelector("#root", {
      state: "attached",
      timeout: 10000,
    });

    await page.waitForTimeout(5000);

    const aaiiHistoryLogs = consoleLogs.filter((log) =>
      log.includes("aaiiHistory")
    );

    const sentimentChartDataLogs = consoleLogs.filter((log) =>
      log.includes("sentimentChartData")
    );
  });
});

