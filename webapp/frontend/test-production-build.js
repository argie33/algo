#!/usr/bin/env node

/**
 * Production Build Validation Test
 * Tests that the built production files can be loaded without runtime errors
 */

import { createServer } from 'http';
import { readFileSync } from 'fs';
import { join } from 'path';
import { chromium } from 'playwright';

const PORT = 8999;
const DIST_DIR = join(process.cwd(), 'dist');

console.log('🧪 Testing production build...');

// Create simple HTTP server to serve built files
const server = createServer((req, res) => {
  let filePath = req.url === '/' ? '/index.html' : req.url;

  // Remove query parameters
  const url = new URL(req.url, `http://localhost:${PORT}`);
  filePath = url.pathname === '/' ? '/index.html' : url.pathname;

  try {
    const fullPath = join(DIST_DIR, filePath);
    const content = readFileSync(fullPath);

    // Set appropriate content type
    if (filePath.endsWith('.js')) {
      res.setHeader('Content-Type', 'application/javascript');
    } else if (filePath.endsWith('.css')) {
      res.setHeader('Content-Type', 'text/css');
    } else if (filePath.endsWith('.html')) {
      res.setHeader('Content-Type', 'text/html');
    } else if (filePath.endsWith('.svg')) {
      res.setHeader('Content-Type', 'image/svg+xml');
    } else if (filePath.endsWith('.json')) {
      res.setHeader('Content-Type', 'application/json');
    }

    res.writeHead(200);
    res.end(content);
  } catch (error) {
    console.log(`404: ${filePath}`);
    res.writeHead(404);
    res.end('Not found');
  }
});

server.listen(PORT, async () => {
  console.log(`📡 Server running on http://localhost:${PORT}`);

  let browser;
  try {
    // Launch browser and test the built app
    browser = await chromium.launch();
    const page = await browser.newPage();

    // Capture console errors
    const errors = [];
    const requests = [];

    page.on('console', msg => {
      if (msg.type() === 'error') {
        const text = msg.text();
        // Ignore network errors for API endpoints - these are application-level, not build errors
        if (text.includes('Failed to load resource') && text.includes('404')) {
          return; // Expected when API returns 404 for missing data
        }
        errors.push(text);
      }
    });

    // Capture uncaught exceptions
    page.on('pageerror', error => {
      errors.push(error.message);
    });

    // Capture failed requests (but ignore expected API 404s)
    page.on('response', response => {
      if (!response.ok()) {
        const url = response.url();
        // Ignore expected API 404s for missing data - these are application-level, not build errors
        if (response.status() === 404 && url.includes('/api/')) {
          return; // This is expected when database has no data
        }
        requests.push(`${response.status()} ${response.url()}`);
      }
    });

    console.log('🚀 Loading production build in browser...');
    await page.goto(`http://localhost:${PORT}`, { waitUntil: 'networkidle' });

    // Wait a bit for any delayed errors
    await page.waitForTimeout(3000);

    if (errors.length > 0 || requests.length > 0) {
      if (requests.length > 0) {
        console.error('❌ Production build has failed requests:');
        requests.forEach(req => console.error(`  • ${req}`));
      }
      if (errors.length > 0) {
        console.error('❌ Production build has runtime errors:');
        errors.forEach(error => console.error(`  • ${error}`));
      }
      process.exit(1);
    } else {
      console.log('✅ Production build loads without runtime errors');
      process.exit(0);
    }

  } catch (error) {
    console.error('❌ Test failed:', error.message);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
    server.close();
  }
});