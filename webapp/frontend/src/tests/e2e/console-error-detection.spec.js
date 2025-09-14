/**
 * Enhanced Console Error Detection with Playwright
 * Replaces Puppeteer-based console monitoring with superior multi-browser testing
 *
 * Features:
 * - Multi-browser console error detection
 * - Intelligent error classification
 * - Real-time error reporting
 * - Network error differentiation
 * - MUI/React specific error detection
 */

import { test, expect } from "@playwright/test";

// Error classification patterns
const ERROR_PATTERNS = {
  mui: /MUI:|@mui\/|Material-UI/i,
  react: /React|ReactDOM|useEffect|useState|JSX/i,
  network: /NetworkError|Failed to fetch|fetch.*failed|CORS|net::/i,
  auth: /401|403|Unauthorized|Authentication|JWT|token/i,
  permission: /denied|forbidden|not allowed/i,
  critical:
    /Maximum call stack|RangeError|TypeError.*undefined|Cannot read prop/i,
  performance: /Performance|slow|timeout|memory|bundle/i,
};

// Ignore patterns for non-critical issues
const IGNORE_PATTERNS = [
  /HTTP ERROR: 304/, // Cached responses
  /DevTools/, // Browser DevTools messages
  /Extension/, // Browser extension messages
  /webpack-dev-server/, // Dev server messages
  /Download the React DevTools/, // React DevTools promotion
  /react-hot-loader/, // Hot reload messages
];

class ConsoleErrorDetector {
  constructor() {
    this.errors = [];
    this.warnings = [];
    this.networkErrors = [];
    this.startTime = Date.now();
  }

  shouldIgnore(message) {
    return IGNORE_PATTERNS.some((pattern) => pattern.test(message));
  }

  classifyError(message) {
    const classification = {};

    Object.entries(ERROR_PATTERNS).forEach(([type, pattern]) => {
      if (pattern.test(message)) {
        classification[type] = true;
      }
    });

    return classification;
  }

  addConsoleMessage(type, message, url = "", lineNumber = 0) {
    if (this.shouldIgnore(message)) return;

    const timestamp = Date.now() - this.startTime;
    const classification = this.classifyError(message);

    const entry = {
      type,
      message,
      url,
      lineNumber,
      timestamp,
      classification,
      severity: this.calculateSeverity(type, message, classification),
    };

    if (type === "error") {
      this.errors.push(entry);
    } else if (type === "warning") {
      this.warnings.push(entry);
    }
  }

  addNetworkError(method, url, status, statusText) {
    // Ignore cached responses and expected redirects
    if (status === 304 || (status >= 300 && status < 400)) return;

    this.networkErrors.push({
      method,
      url,
      status,
      statusText,
      timestamp: Date.now() - this.startTime,
      severity: status >= 500 ? "critical" : status >= 400 ? "high" : "medium",
    });
  }

  calculateSeverity(type, message, classification) {
    if (type === "error" && classification.critical) return "critical";
    if (type === "error" && (classification.react || classification.mui))
      return "high";
    if (type === "error") return "medium";
    if (type === "warning" && classification.performance) return "medium";
    return "low";
  }

  generateReport() {
    const totalErrors = this.errors.length;
    const totalWarnings = this.warnings.length;
    const totalNetworkErrors = this.networkErrors.length;
    const totalIssues = totalErrors + totalWarnings + totalNetworkErrors;

    const criticalErrors = this.errors.filter((e) => e.severity === "critical");
    const highErrors = this.errors.filter((e) => e.severity === "high");

    return {
      summary: {
        totalIssues,
        totalErrors,
        totalWarnings,
        totalNetworkErrors,
        criticalErrors: criticalErrors.length,
        highErrors: highErrors.length,
        testDurationMs: Date.now() - this.startTime,
      },
      errors: this.errors,
      warnings: this.warnings,
      networkErrors: this.networkErrors,
      recommendations: this.generateRecommendations(),
    };
  }

  generateRecommendations() {
    const recommendations = [];

    const muiErrors = this.errors.filter((e) => e.classification.mui);
    if (muiErrors.length > 0) {
      recommendations.push({
        type: "mui",
        priority: "high",
        message: `Found ${muiErrors.length} MUI-related errors. Check Material-UI version compatibility.`,
      });
    }

    const reactErrors = this.errors.filter((e) => e.classification.react);
    if (reactErrors.length > 0) {
      recommendations.push({
        type: "react",
        priority: "high",
        message: `Found ${reactErrors.length} React-related errors. Check component lifecycle and hooks usage.`,
      });
    }

    const networkErrors = this.networkErrors.filter((e) => e.status >= 400);
    if (networkErrors.length > 0) {
      recommendations.push({
        type: "network",
        priority: "medium",
        message: `Found ${networkErrors.length} API errors. Check backend connectivity and authentication.`,
      });
    }

    return recommendations;
  }
}

test.describe("Console Error Detection", () => {
  let detector;

  test.beforeEach(async ({ page }) => {
    detector = new ConsoleErrorDetector();

    // Enhanced console monitoring
    page.on("console", (msg) => {
      const type = msg.type();
      const text = msg.text();
      const url = msg.location()?.url || "";
      const lineNumber = msg.location()?.lineNumber || 0;

      detector.addConsoleMessage(type, text, url, lineNumber);
    });

    // Page error monitoring (JavaScript runtime errors)
    page.on("pageerror", (error) => {
      detector.addConsoleMessage(
        "error",
        `JavaScript Runtime Error: ${error.message}`
      );
    });

    // Network error monitoring
    page.on("response", (response) => {
      if (!response.ok() && response.status() !== 304) {
        detector.addNetworkError(
          response.request().method(),
          response.url(),
          response.status(),
          response.statusText()
        );
      }
    });

    page.on("requestfailed", (request) => {
      const failure = request.failure();
      if (failure) {
        detector.addNetworkError(
          request.method(),
          request.url(),
          0,
          failure.errorText
        );
      }
    });
  });

  // Test key application pages for console errors
  const PAGES_TO_TEST = [
    { name: "Homepage", path: "/" },
    { name: "Dashboard", path: "/dashboard" },
    { name: "Portfolio", path: "/portfolio" },
    { name: "Market Overview", path: "/market" },
    { name: "Settings", path: "/settings" },
    { name: "Watchlist", path: "/watchlist" },
    { name: "Trading Signals", path: "/trading-signals" },
    { name: "News Sentiment", path: "/sentiment/news" },
    { name: "Sector Analysis", path: "/sectors" },
    { name: "Economic Data", path: "/economic" },
  ];

  PAGES_TO_TEST.forEach((pageInfo) => {
    test(`should have no critical console errors on ${pageInfo.name}`, async ({
      page,
    }) => {
      // Navigate to the page
      await page.goto(pageInfo.path, {
        waitUntil: "domcontentloaded",
        timeout: 15000,
      });

      // Wait for React app to fully load and render
      await page.waitForTimeout(3000);

      // Try to interact with the page to trigger dynamic loading
      try {
        // Scroll to trigger lazy loading
        await page.evaluate(() => {
          window.scrollTo(0, document.body.scrollHeight / 2);
        });
        await page.waitForTimeout(1000);

        // Click first button if available (non-destructive actions only)
        const buttons = page.locator(
          'button:not([type="submit"]):not(.delete):not(.remove)'
        );
        const buttonCount = await buttons.count();
        if (buttonCount > 0) {
          await buttons
            .first()
            .click({ timeout: 2000 })
            .catch(() => {
              // Ignore interaction failures, focus on console errors
            });
          await page.waitForTimeout(1000);
        }

        // Hover over navigation items to trigger any hover effects
        const navItems = page.locator('nav a, [role="navigation"] a').first();
        if ((await navItems.count()) > 0) {
          await navItems.hover({ timeout: 2000 }).catch(() => {
            // Ignore hover failures
          });
        }
      } catch (interactionError) {
        // Interactions are secondary to console error detection
        console.log(
          `Note: Could not interact with ${pageInfo.name}: ${interactionError.message}`
        );
      }

      // Wait for any async operations to complete
      await page.waitForTimeout(2000);

      // Generate the error report
      const report = detector.generateReport();

      // Log detailed results for debugging
      console.log(`\n📊 Console Error Report for ${pageInfo.name}:`);
      console.log(`   Total Issues: ${report.summary.totalIssues}`);
      console.log(
        `   Errors: ${report.summary.totalErrors} (${report.summary.criticalErrors} critical)`
      );
      console.log(`   Warnings: ${report.summary.totalWarnings}`);
      console.log(`   Network Errors: ${report.summary.totalNetworkErrors}`);

      if (report.errors.length > 0) {
        console.log("\n❌ Console Errors:");
        report.errors.forEach((error, i) => {
          console.log(`   ${i + 1}. [${error.severity}] ${error.message}`);
          if (Object.keys(error.classification).length > 0) {
            console.log(
              `      Types: ${Object.keys(error.classification).join(", ")}`
            );
          }
        });
      }

      if (report.warnings.length > 0 && report.warnings.length <= 5) {
        console.log("\n⚠️ Console Warnings:");
        report.warnings.forEach((warning, i) => {
          console.log(`   ${i + 1}. ${warning.message.substring(0, 100)}...`);
        });
      }

      if (report.recommendations.length > 0) {
        console.log("\n💡 Recommendations:");
        report.recommendations.forEach((rec, i) => {
          console.log(`   ${i + 1}. [${rec.priority}] ${rec.message}`);
        });
      }

      // Test assertions
      expect(
        report.summary.criticalErrors,
        `Critical console errors found on ${pageInfo.name}. Check the detailed log above.`
      ).toBe(0);

      // Allow up to 2 high-severity errors (often due to missing API keys in test environment)
      expect(
        report.summary.highErrors,
        `Too many high-severity console errors on ${pageInfo.name}. Maximum 2 allowed for test environment.`
      ).toBeLessThanOrEqual(2);

      // Network errors should be minimal (some expected due to test environment)
      expect(
        report.summary.totalNetworkErrors,
        `Excessive network errors on ${pageInfo.name}. Maximum 3 allowed for test environment.`
      ).toBeLessThanOrEqual(3);
    });
  });

  // Comprehensive multi-page flow test
  test("should maintain low error count during full user journey", async ({
    page,
  }) => {
    const journeyPages = [
      "/",
      "/dashboard",
      "/portfolio",
      "/market",
      "/settings",
    ];

    console.log("\n🚀 Starting comprehensive user journey test...");

    for (const pagePath of journeyPages) {
      await page.goto(pagePath, {
        waitUntil: "domcontentloaded",
        timeout: 10000,
      });
      await page.waitForTimeout(2000);
    }

    const finalReport = detector.generateReport();

    console.log("\n📊 Complete User Journey Report:");
    console.log(`   Pages Visited: ${journeyPages.length}`);
    console.log(
      `   Total Test Duration: ${finalReport.summary.testDurationMs}ms`
    );
    console.log(`   Total Issues: ${finalReport.summary.totalIssues}`);
    console.log(`   Critical Errors: ${finalReport.summary.criticalErrors}`);
    console.log(`   High-Severity Errors: ${finalReport.summary.highErrors}`);

    // Stricter requirements for full journey
    expect(finalReport.summary.criticalErrors).toBe(0);
    expect(finalReport.summary.highErrors).toBeLessThanOrEqual(3);
    expect(finalReport.summary.totalErrors).toBeLessThanOrEqual(5);
  });
});

// Export the detector class for use in other tests
export { ConsoleErrorDetector, ERROR_PATTERNS };
