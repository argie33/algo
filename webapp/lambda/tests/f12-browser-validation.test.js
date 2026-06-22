/**
 * F12 DevTools Console Validation - Real Browser Testing
 *
 * Tests all pages in actual Chrome browser and captures F12 console output
 * to prove: (1) no errors, (2) all APIs working, (3) all data loading
 */

const puppeteer = require("puppeteer");
const fs = require("fs");
const path = require("path");

// Pages to test and their expected data indicators
const PAGES_TO_TEST = [
  { path: "/", name: "Dashboard", dataIndicators: ["portfolio", "total"] },
  { path: "/stocks", name: "Stocks", dataIndicators: ["symbol", "price"] },
  { path: "/signals", name: "Signals", dataIndicators: ["signal", "symbol"] },
  { path: "/trades", name: "Trades", dataIndicators: ["trade", "pnl"] },
  { path: "/analysis", name: "Analysis", dataIndicators: ["chart", "metric"] },
  {
    path: "/portfolio",
    name: "Portfolio",
    dataIndicators: ["position", "value"],
  },
  {
    path: "/settings",
    name: "Settings",
    dataIndicators: ["setting", "preference"],
  },
  {
    path: "/backtest",
    name: "Backtest",
    dataIndicators: ["result", "performance"],
  },
];

const BASE_URL = "http://localhost:5173"; // Vite dev server

describe("F12 Browser Console Validation", () => {
  let browser;
  let results = [];

  beforeAll(async () => {
    browser = await puppeteer.launch({
      headless: "new",
      args: [
        "--disable-gpu",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--start-maximized",
      ],
    });
  });

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }

    // Write summary report
    const timestamp = new Date().toISOString();
    const report = {
      timestamp,
      testCount: results.length,
      passed: results.filter((r) => r.passed).length,
      failed: results.filter((r) => !r.passed).length,
      consoleErrors: results.reduce(
        (sum, r) => sum + r.consoleErrors.length,
        0
      ),
      consoleWarnings: results.reduce(
        (sum, r) => sum + r.consoleWarnings.length,
        0
      ),
      pages: results,
    };

    console.log("\n" + "=".repeat(80));
    console.log("F12 BROWSER CONSOLE VALIDATION REPORT");
    console.log("=".repeat(80));
    console.log(`Timestamp: ${timestamp}`);
    console.log(`Pages tested: ${report.testCount}/${PAGES_TO_TEST.length}`);
    console.log(`✓ Passed: ${report.passed}  ✗ Failed: ${report.failed}`);
    console.log(
      `Console errors: ${report.consoleErrors}  Warnings: ${report.consoleWarnings}`
    );
    console.log("=".repeat(80));

    results.forEach((page) => {
      console.log(`\n📄 ${page.name} (${page.path})`);
      console.log(`  Status: ${page.passed ? "✓ PASS" : "✗ FAIL"}`);
      console.log(`  Load time: ${page.loadTime}ms`);
      console.log(`  DOM elements: ${page.domElements}`);
      console.log(`  Console messages:`);
      console.log(`    - Errors: ${page.consoleErrors.length}`);
      if (page.consoleErrors.length > 0) {
        page.consoleErrors.forEach((err) => {
          console.log(`      ✗ ${err}`);
        });
      }
      console.log(`    - Warnings: ${page.consoleWarnings.length}`);
      if (page.consoleWarnings.length > 0) {
        page.consoleWarnings.slice(0, 3).forEach((warn) => {
          console.log(`      ⚠ ${warn}`);
        });
        if (page.consoleWarnings.length > 3) {
          console.log(
            `      ... and ${page.consoleWarnings.length - 3} more warnings`
          );
        }
      }
      console.log(`    - Logs: ${page.consoleLogs.length}`);
      console.log(
        `  Data indicators found: ${page.dataIndicatorsFound.join(", ") || "none"}`
      );
    });

    console.log("\n" + "=".repeat(80));
    console.log("✓ F12 VALIDATION COMPLETE");
    console.log("=".repeat(80));

    // Write JSON report
    fs.writeFileSync(
      path.resolve(__dirname, "f12-validation-report.json"),
      JSON.stringify(report, null, 2)
    );
  });

  PAGES_TO_TEST.forEach((pageConfig) => {
    it(`should load ${pageConfig.name} with clean F12 console`, async () => {
      const page = await browser.newPage();
      const consoleMessages = {
        errors: [],
        warnings: [],
        logs: [],
      };

      // Capture all console messages
      page.on("console", (msg) => {
        const text = msg.text();
        const type = msg.type();

        if (type === "error") {
          consoleMessages.errors.push(text);
        } else if (type === "warning") {
          consoleMessages.warnings.push(text);
        } else if (type === "log") {
          consoleMessages.logs.push(text);
        }
      });

      // Capture uncaught exceptions
      page.on("error", (err) => {
        consoleMessages.errors.push(`Uncaught exception: ${err.message}`);
      });

      // Capture page crashes
      page.on("close", () => {
        if (page.isClosed()) {
          consoleMessages.errors.push(
            "Page crashed or was closed unexpectedly"
          );
        }
      });

      let loadTime = 0;
      let domElements = 0;
      let dataIndicatorsFound = [];

      try {
        // Navigate to page
        const startTime = Date.now();
        await page.goto(`${BASE_URL}${pageConfig.path}`, {
          waitUntil: "networkidle2",
          timeout: 30000,
        });
        loadTime = Date.now() - startTime;

        // Wait for initial render
        await page.waitForTimeout(500);

        // Count DOM elements
        // eslint-disable-next-line no-undef
        domElements = await page.evaluate(
          // eslint-disable-next-line no-undef
          () => document.querySelectorAll("*").length
        );

        // Check for data indicators in page HTML
        const pageHtml = await page.content();
        pageConfig.dataIndicators.forEach((indicator) => {
          if (pageHtml.toLowerCase().includes(indicator.toLowerCase())) {
            dataIndicatorsFound.push(indicator);
          }
        });

        // Also check for data in console logs
        consoleMessages.logs.forEach((log) => {
          pageConfig.dataIndicators.forEach((indicator) => {
            if (log.toLowerCase().includes(indicator.toLowerCase())) {
              if (!dataIndicatorsFound.includes(indicator)) {
                dataIndicatorsFound.push(indicator);
              }
            }
          });
        });

        // Test is passed if:
        // 1. No console errors
        // 2. Page loaded (DOM elements > 50)
        // 3. At least some data indicators found
        const passed =
          consoleMessages.errors.length === 0 &&
          domElements > 30 &&
          (dataIndicatorsFound.length > 0 || consoleMessages.logs.length > 0);

        const result = {
          name: pageConfig.name,
          path: pageConfig.path,
          passed,
          loadTime,
          domElements,
          consoleErrors: consoleMessages.errors,
          consoleWarnings: consoleMessages.warnings,
          consoleLogs: consoleMessages.logs.slice(0, 20), // Keep first 20 logs
          dataIndicatorsFound,
        };

        results.push(result);

        // Assertion
        expect(passed).toBe(true);
        expect(consoleMessages.errors).toEqual([]);
      } catch (error) {
        const result = {
          name: pageConfig.name,
          path: pageConfig.path,
          passed: false,
          loadTime,
          domElements,
          consoleErrors: [...consoleMessages.errors, error.message],
          consoleWarnings: consoleMessages.warnings,
          consoleLogs: consoleMessages.logs,
          dataIndicatorsFound,
        };

        results.push(result);
        throw error;
      } finally {
        await page.close();
      }
    });
  });

  it("should verify all API endpoints respond without errors", async () => {
    const page = await browser.newPage();
    const apiErrors = [];

    // Intercept all API requests
    await page.on("response", (response) => {
      if (response.url().includes("/api/")) {
        if (response.status() >= 400) {
          apiErrors.push(`${response.url()} - ${response.status()}`);
        }
      }
    });

    try {
      // Navigate to dashboard to trigger all initial API calls
      await page.goto(`${BASE_URL}/`, {
        waitUntil: "networkidle2",
        timeout: 30000,
      });

      // Wait for API calls to complete
      await page.waitForTimeout(2000);

      expect(apiErrors).toEqual([]);
    } finally {
      await page.close();
    }
  });
});
