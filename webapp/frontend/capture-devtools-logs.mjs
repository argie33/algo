import { chromium } from "playwright";
import fs from "fs";

const OUTPUT_FILE = "devtools-logs.json";

async function captureDevToolsLogs() {
  let browser;
  const logs = {
    timestamp: new Date().toISOString(),
    console: [],
    network: [],
    errors: [],
    performance: {},
    pageMetrics: {},
  };

  try {
    browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();

    // Capture console messages
    page.on("console", (msg) => {
      logs.console.push({
        type: msg.type(),
        text: msg.text(),
        location: msg.location(),
        args: msg.args().length,
      });
    });

    // Capture network requests
    page.on("request", (request) => {
      logs.network.push({
        method: request.method(),
        url: request.url(),
        resourceType: request.resourceType(),
        postData: request.postData(),
      });
    });

    // Capture network responses
    page.on("response", (response) => {
      logs.network[logs.network.length - 1] = {
        ...logs.network[logs.network.length - 1],
        status: response.status(),
        statusText: response.statusText(),
      };
    });

    // Capture page errors
    page.on("pageerror", (error) => {
      logs.errors.push({
        name: error.name,
        message: error.message,
        stack: error.stack,
      });
    });

    // Capture request failures
    page.on("requestfailed", (request) => {
      logs.errors.push({
        type: "request_failed",
        url: request.url(),
        failure: request.failure(),
      });
    });

    // Get API_URL from environment
    const apiUrl =
      process.env.REACT_APP_API_URL || "http://localhost:8000/api";
    const frontendUrl = process.env.REACT_APP_FRONTEND_URL || apiUrl.replace("/api", "");

    console.log(`Navigating to ${frontendUrl}...`);

    try {
      await page.goto(frontendUrl, { waitUntil: "networkidle", timeout: 30000 });
    } catch (e) {
      logs.errors.push({
        type: "navigation_error",
        message: e.message,
      });
    }

    // Wait a moment for any async operations
    await page.waitForTimeout(3000);

    // Capture performance metrics
    const metrics = await page.metrics();
    logs.pageMetrics = metrics;

    // Check for any 500/400 errors
    const failedRequests = logs.network.filter((r) => r.status >= 400);
    if (failedRequests.length > 0) {
      logs.errors.push({
        type: "http_errors",
        requests: failedRequests,
      });
    }

    // Evaluate page for client-side errors
    const clientErrors = await page.evaluate(() => {
      return {
        localStorage: Object.keys(localStorage)
          .map((k) => ({ key: k, value: localStorage.getItem(k) }))
          .slice(0, 10),
        sessionStorage: Object.keys(sessionStorage)
          .map((k) => ({ key: k, value: sessionStorage.getItem(k) }))
          .slice(0, 10),
        title: document.title,
        url: window.location.href,
      };
    });
    logs.clientState = clientErrors;

    await context.close();
  } catch (error) {
    logs.errors.push({
      type: "script_error",
      message: error.message,
      stack: error.stack,
    });
  } finally {
    if (browser) {
      await browser.close();
    }
  }

  // Write results to file
  fs.writeFileSync(OUTPUT_FILE, JSON.stringify(logs, null, 2));
  console.log(`\n✅ DevTools logs captured to ${OUTPUT_FILE}`);
  console.log(`\nSummary:`);
  console.log(`  Console messages: ${logs.console.length}`);
  console.log(`  Network requests: ${logs.network.length}`);
  console.log(`  Errors: ${logs.errors.length}`);
  console.log(`  Performance:`);
  console.log(`    - JSHeapUsedSize: ${(logs.pageMetrics.JSHeapUsedSize / 1024 / 1024).toFixed(2)} MB`);
  console.log(`    - NetworkReceived: ${(logs.pageMetrics.NetworkReceived / 1024).toFixed(2)} KB`);

  // Print errors
  if (logs.errors.length > 0) {
    console.log(`\n⚠️ Errors Found:`);
    logs.errors.forEach((e) => {
      console.log(`  - ${e.type || e.name}: ${e.message}`);
    });
  }

  // Print failed HTTP requests
  const failedReqs = logs.network.filter((r) => r.status >= 400);
  if (failedReqs.length > 0) {
    console.log(`\n❌ Failed HTTP Requests:`);
    failedReqs.forEach((r) => {
      console.log(`  - ${r.status} ${r.method} ${r.url}`);
    });
  }
}

captureDevToolsLogs().catch(console.error);
