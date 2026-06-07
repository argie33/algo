#!/usr/bin/env node

import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';

const FRONTEND_URL = 'http://localhost:5173';
const BACKEND_URL = 'http://localhost:3001';

const pages = [
  { route: '/app/markets', name: 'Market Health' },
  { route: '/app/sectors', name: 'Sector Analysis' },
  { route: '/app/swing', name: 'Swing Candidates' },
  { route: '/app/scores', name: 'Stock Scores' },
  { route: '/app/trading-signals', name: 'Trading Signals' },
  { route: '/app/sentiment', name: 'Sentiment Analysis' },
  { route: '/app/portfolio', name: 'Portfolio' },
  { route: '/app', name: 'Dashboard (default)' }
];

const results = {
  timestamp: new Date().toISOString(),
  frontend_url: FRONTEND_URL,
  backend_url: BACKEND_URL,
  pages: {}
};

const browser = await chromium.launch({ headless: true });

console.log('🔍 FULL SITE DIAGNOSTIC - Checking for 5xx errors, React errors, data loading issues\n');
console.log('═'.repeat(100));

for (const pageInfo of pages) {
  const url = FRONTEND_URL + pageInfo.route;
  const pageResults = {
    url: url,
    timestamp: new Date().toISOString(),
    console_logs: [],
    network_errors: [],
    http_errors: [],
    api_failures: [],
    react_errors: [],
    warnings: [],
    data_issues: [],
    page_content: null
  };

  const page = await browser.newPage();

  // Capture all console messages
  page.on('console', msg => {
    pageResults.console_logs.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location()
    });
  });

  // Capture all network responses
  page.on('response', response => {
    const status = response.status();
    if (status >= 400) {
      pageResults.http_errors.push({
        url: response.url(),
        status: status,
        statusText: response.statusText()
      });
    }
  });

  // Capture request failures
  page.on('requestfailed', request => {
    pageResults.network_errors.push({
      url: request.url(),
      failure: request.failure().errorText
    });
  });

  try {
    console.log(`\n⏳ Loading: ${pageInfo.name} (${pageInfo.route})`);

    const response = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    console.log(`   Status: ${response.status()} ${response.statusText()}`);

    // Wait a bit more for async operations
    await page.waitForTimeout(2000);

    // Check for React errors via window.__REACT_ERROR__
    const reactErrors = await page.evaluate(() => {
      const errors = [];

      // Check for React 18 error boundary catches
      if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__?.currentFiber?.memoizedState) {
        errors.push('React error boundary detected');
      }

      // Check for unhandled promise rejections
      const unhandledErrors = window.__unhandledErrors || [];
      if (Array.isArray(unhandledErrors)) {
        errors.push(...unhandledErrors);
      }

      return errors;
    });

    if (reactErrors.length > 0) {
      pageResults.react_errors.push(...reactErrors);
    }

    // Analyze page content
    const pageAnalysis = await page.evaluate(() => {
      const analysis = {
        has_main_content: false,
        has_loading_spinner: false,
        has_error_message: false,
        empty_containers: [],
        missing_data_elements: [],
        text_content_length: 0,
        charts_count: 0,
        tables_count: 0,
        images_count: 0
      };

      // Check main content
      const main = document.querySelector('main') || document.querySelector('[role="main"]');
      if (main) {
        analysis.has_main_content = true;
        analysis.text_content_length = main.innerText.length;
      }

      // Check for loading indicators
      analysis.has_loading_spinner = document.querySelector('[class*="loader"], [class*="spinner"], [class*="loading"]') !== null;

      // Check for error messages
      analysis.has_error_message = document.querySelector('[class*="error"]') !== null;

      // Count data visualization elements
      analysis.charts_count = document.querySelectorAll('svg, [class*="chart"], [class*="Chart"]').length;
      analysis.tables_count = document.querySelectorAll('table tbody tr').length;
      analysis.images_count = document.querySelectorAll('img').length;

      // Check for empty containers (potential data loading issues)
      document.querySelectorAll('[class*="container"], [class*="card"], [class*="Card"]').forEach((el) => {
        if (el.innerText.trim().length === 0 && el.children.length === 0) {
          analysis.empty_containers.push(el.className || el.id || 'unknown');
        }
      });

      // Look for "undefined", "null", "error" text content
      const bodyText = document.body.innerText.toLowerCase();
      if (bodyText.includes('undefined')) analysis.missing_data_elements.push('undefined');
      if (bodyText.includes('null')) analysis.missing_data_elements.push('null');
      if (bodyText.includes('error loading') || bodyText.includes('failed to load')) analysis.missing_data_elements.push('error text');

      return analysis;
    });

    pageResults.page_content = pageAnalysis;

    // Filter and categorize errors
    pageResults.console_logs.forEach(log => {
      if (log.type === 'error') {
        const text = log.text.toLowerCase();
        if (text.includes('404') || text.includes('5xx') || text.includes('500') || text.includes('502') || text.includes('503')) {
          pageResults.http_errors.push({ type: 'console', message: log.text });
        } else if (text.includes('api') || text.includes('fetch') || text.includes('axios')) {
          pageResults.api_failures.push(log.text);
        } else if (text.includes('react') || text.includes('component') || text.includes('render')) {
          pageResults.react_errors.push(log.text);
        } else {
          pageResults.data_issues.push(log.text);
        }
      } else if (log.type === 'warning') {
        pageResults.warnings.push(log.text);
      }
    });

    console.log(`   ✅ Page loaded successfully`);
    if (pageAnalysis.text_content_length > 100) {
      console.log(`   ✅ Content present (${pageAnalysis.text_content_length} chars)`);
    } else {
      console.log(`   ⚠️  Minimal content (${pageAnalysis.text_content_length} chars)`);
    }

    if (pageResults.http_errors.length > 0) {
      console.log(`   ❌ HTTP Errors: ${pageResults.http_errors.length}`);
    }
    if (pageResults.api_failures.length > 0) {
      console.log(`   ❌ API Failures: ${pageResults.api_failures.length}`);
    }
    if (pageResults.react_errors.length > 0) {
      console.log(`   ❌ React Errors: ${pageResults.react_errors.length}`);
    }
    if (pageResults.network_errors.length > 0) {
      console.log(`   ❌ Network Errors: ${pageResults.network_errors.length}`);
    }

  } catch (err) {
    console.log(`   ❌ Failed to load: ${err.message}`);
    pageResults.error = err.message;
  } finally {
    await page.close();
  }

  results.pages[pageInfo.name] = pageResults;
}

await browser.close();

// Write results to file
const reportPath = path.join('C:\\Users\\arger\\code\\algo', 'DIAGNOSTIC_REPORT.md');
let markdown = `# Full Site Diagnostic Report\n\n`;
markdown += `**Generated:** ${new Date().toLocaleString()}\n\n`;
markdown += `**Frontend:** ${FRONTEND_URL}\n`;
markdown += `**Backend:** ${BACKEND_URL}\n\n`;
markdown += `## Summary\n\n`;

let totalErrors = 0;
let totalWarnings = 0;
let pagesWithIssues = 0;

for (const [pageName, pageData] of Object.entries(results.pages)) {
  const errorCount = pageData.http_errors.length + pageData.api_failures.length + pageData.react_errors.length + pageData.network_errors.length;
  const warningCount = pageData.warnings.length + pageData.data_issues.length;

  if (errorCount > 0 || warningCount > 0) {
    pagesWithIssues++;
  }

  totalErrors += errorCount;
  totalWarnings += warningCount;
}

markdown += `- **Pages Checked:** ${Object.keys(results.pages).length}\n`;
markdown += `- **Pages with Issues:** ${pagesWithIssues}\n`;
markdown += `- **Total Errors Found:** ${totalErrors}\n`;
markdown += `- **Total Warnings Found:** ${totalWarnings}\n\n`;

// Detailed issues by page
markdown += `## Issues by Page\n\n`;

for (const [pageName, pageData] of Object.entries(results.pages)) {
  const hasErrors = pageData.http_errors.length > 0 || pageData.api_failures.length > 0 || pageData.react_errors.length > 0 || pageData.network_errors.length > 0;
  const hasWarnings = pageData.warnings.length > 0 || pageData.data_issues.length > 0;

  if (!hasErrors && !hasWarnings) continue;

  markdown += `### ${pageName}\n\n`;
  markdown += `**URL:** ${pageData.url}\n\n`;

  if (pageData.error) {
    markdown += `**Failed to Load:** ${pageData.error}\n\n`;
    continue;
  }

  // HTTP Errors
  if (pageData.http_errors.length > 0) {
    markdown += `#### HTTP/Network Errors (${pageData.http_errors.length})\n\n`;
    pageData.http_errors.slice(0, 10).forEach(err => {
      if (err.status) {
        markdown += `- **${err.status}** ${err.statusText || ''} - ${err.url}\n`;
      } else {
        markdown += `- ${err.message}\n`;
      }
    });
    markdown += `\n`;
  }

  // API Failures
  if (pageData.api_failures.length > 0) {
    markdown += `#### API Failures (${pageData.api_failures.length})\n\n`;
    pageData.api_failures.slice(0, 10).forEach(err => {
      markdown += `- ${err.substring(0, 150)}\n`;
    });
    markdown += `\n`;
  }

  // React Errors
  if (pageData.react_errors.length > 0) {
    markdown += `#### React/Component Errors (${pageData.react_errors.length})\n\n`;
    pageData.react_errors.slice(0, 10).forEach(err => {
      markdown += `- ${err.substring(0, 150)}\n`;
    });
    markdown += `\n`;
  }

  // Network Errors
  if (pageData.network_errors.length > 0) {
    markdown += `#### Network Request Failures (${pageData.network_errors.length})\n\n`;
    pageData.network_errors.slice(0, 10).forEach(err => {
      markdown += `- ${err.url}\n  Reason: ${err.failure}\n`;
    });
    markdown += `\n`;
  }

  // Data Issues
  if (pageData.data_issues.length > 0) {
    markdown += `#### Data/Display Issues (${pageData.data_issues.length})\n\n`;
    pageData.data_issues.slice(0, 5).forEach(issue => {
      markdown += `- ${issue.substring(0, 150)}\n`;
    });
    markdown += `\n`;
  }

  // Page Content Analysis
  if (pageData.page_content) {
    const content = pageData.page_content;
    markdown += `#### Content Analysis\n\n`;
    markdown += `- Main Content Present: ${content.has_main_content ? '✓' : '✗'}\n`;
    markdown += `- Text Content: ${content.text_content_length} characters\n`;
    markdown += `- Charts: ${content.charts_count}\n`;
    markdown += `- Tables: ${content.tables_count}\n`;
    markdown += `- Images: ${content.images_count}\n`;
    if (content.empty_containers.length > 0) {
      markdown += `- **Empty Containers:** ${content.empty_containers.length} found\n`;
    }
    if (content.missing_data_elements.length > 0) {
      markdown += `- **Missing Data Indicators:** ${content.missing_data_elements.join(', ')}\n`;
    }
    markdown += `\n`;
  }

  // Console Warnings
  if (pageData.warnings.length > 0) {
    markdown += `#### Console Warnings (${pageData.warnings.length})\n\n`;
    pageData.warnings.slice(0, 5).forEach(warn => {
      markdown += `- ${warn.substring(0, 150)}\n`;
    });
    markdown += `\n`;
  }
}

// Raw JSON for reference
markdown += `\n## Raw Data (JSON)\n\n\`\`\`json\n`;
markdown += JSON.stringify(results, null, 2);
markdown += `\n\`\`\`\n`;

fs.writeFileSync(reportPath, markdown);
console.log(`\n\n${'═'.repeat(100)}`);
console.log(`\n📋 Report saved to: ${reportPath}\n`);
console.log(`📊 Summary:`);
console.log(`   Pages checked: ${Object.keys(results.pages).length}`);
console.log(`   Pages with issues: ${pagesWithIssues}`);
console.log(`   Total errors: ${totalErrors}`);
console.log(`   Total warnings: ${totalWarnings}`);
