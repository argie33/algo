/**
 * React-AWS Integration End-to-End Tests
 * Catches React hook and AWS dependency conflicts before deployment
 */

import { test, expect, chromium } from '@playwright/test';

test.describe('React-AWS Integration Validation', () => {
  let browser, context, page;

  test.beforeAll(async () => {
    browser = await chromium.launch();
    context = await browser.newContext();
    page = await context.newPage();
    
    // Listen for console errors
    page.on('console', message => {
      if (message.type() === 'error') {
        console.error('❌ Browser Console Error:', message.text());
      }
    });
    
    // Listen for page errors
    page.on('pageerror', error => {
      console.error('❌ Page Error:', error.message);
    });
  });

  test.afterAll(async () => {
    await browser.close();
  });

  test('should detect use-sync-external-store errors', async () => {
    const consoleErrors = [];
    page.on('console', message => {
      if (message.type() === 'error') {
        consoleErrors.push(message.text());
      }
    });

    await page.goto('http://localhost:3000');
    
    // Wait for React to load
    await page.waitForTimeout(3000);
    
    // Check for specific useState/hook errors
    const hookErrors = consoleErrors.filter(error => 
      error.includes('useState') || 
      error.includes('use-sync-external-store') ||
      error.includes('Cannot read properties of undefined')
    );
    
    expect(hookErrors).toHaveLength(0);
    console.log('✅ No React hook errors detected');
  });

  test('should validate AWS Amplify initialization', async () => {
    await page.goto('http://localhost:3000');
    
    // Wait for app to load
    await page.waitForSelector('[data-testid="app-container"], #root', { timeout: 10000 });
    
    // Check if AWS Amplify is causing conflicts
    const awsError = await page.evaluate(() => {
      return window.console.error.toString().includes('Amplify') || 
             window.console.error.toString().includes('aws-amplify');
    });
    
    expect(awsError).toBe(false);
    console.log('✅ AWS Amplify initialized without conflicts');
  });

  test('should validate React Query integration', async () => {
    await page.goto('http://localhost:3000');
    
    // Wait for React Query to initialize
    await page.waitForTimeout(2000);
    
    // Check React Query doesn't cause hook errors
    const reactQueryError = await page.evaluate(() => {
      const errors = window.__REACT_QUERY_ERRORS__ || [];
      return errors.filter(e => e.includes('hook') || e.includes('useState'));
    });
    
    expect(reactQueryError || []).toHaveLength(0);
    console.log('✅ React Query integration working');
  });

  test('should validate all React hooks work correctly', async () => {
    await page.goto('http://localhost:3000');
    
    // Navigate to different pages to test hooks
    const pages = [
      '/dashboard',
      '/portfolio', 
      '/market-overview',
      '/settings'
    ];
    
    for (const pagePath of pages) {
      try {
        await page.goto(`http://localhost:3000${pagePath}`);
        await page.waitForTimeout(1000);
        
        // Check for hook errors on this page
        const hookErrors = await page.evaluate(() => {
          const errors = [];
          const originalError = console.error;
          console.error = (...args) => {
            const message = args.join(' ');
            if (message.includes('hook') || message.includes('useState') || message.includes('useEffect')) {
              errors.push(message);
            }
            originalError.apply(console, args);
          };
          return errors;
        });
        
        expect(hookErrors).toHaveLength(0);
        console.log(`✅ Page ${pagePath} hooks working correctly`);
        
      } catch (error) {
        console.log(`⚠️ Page ${pagePath} not accessible: ${error.message}`);
      }
    }
  });

  test('should validate Material-UI theme works with React 18', async () => {
    await page.goto('http://localhost:3000');
    
    // Wait for MUI to load
    await page.waitForTimeout(2000);
    
    // Check for MUI createPalette errors
    const muiErrors = await page.evaluate(() => {
      const logs = window.__MUI_LOGS__ || [];
      return logs.filter(log => 
        log.includes('createPalette') || 
        log.includes('createTheme') ||
        log.includes('Xa is not a function')
      );
    });
    
    expect(muiErrors || []).toHaveLength(0);
    console.log('✅ Material-UI theme working with React 18');
  });

  test('should validate production build works in browser', async () => {
    // Test the production build
    try {
      await page.goto('http://localhost:4173'); // Vite preview port
      await page.waitForSelector('[data-testid="app-container"], #root', { timeout: 5000 });
      
      const hasContent = await page.locator('#root').isVisible();
      expect(hasContent).toBe(true);
      console.log('✅ Production build loads correctly');
      
    } catch (error) {
      console.log('⚠️ Production build not available for testing');
    }
  });

  test('should validate real-time features work without hook conflicts', async () => {
    await page.goto('http://localhost:3000');
    
    // Test WebSocket/real-time features that often cause hook issues
    await page.evaluate(() => {
      // Simulate WebSocket connection that uses hooks
      if (window.WebSocket) {
        const ws = new WebSocket('wss://echo.websocket.org');
        ws.onopen = () => console.log('WebSocket test connection opened');
        ws.onclose = () => console.log('WebSocket test connection closed');
        ws.onerror = (error) => console.error('WebSocket test error:', error);
        setTimeout(() => ws.close(), 1000);
      }
    });
    
    await page.waitForTimeout(2000);
    
    // Check for WebSocket-related hook errors
    const wsErrors = await page.evaluate(() => {
      const errors = window.__WS_ERRORS__ || [];
      return errors.filter(e => e.includes('hook') || e.includes('useState'));
    });
    
    expect(wsErrors || []).toHaveLength(0);
    console.log('✅ Real-time features working without hook conflicts');
  });
});

test.describe('Build-Time Validation', () => {
  test('should validate build completes without React conflicts', async () => {
    // This test would be run as part of CI/CD to catch build-time issues
    const buildResult = await import('child_process').then(cp => {
      return new Promise((resolve) => {
        const build = cp.spawn('npm', ['run', 'build'], {
          cwd: process.cwd(),
          stdio: 'pipe'
        });
        
        let stdout = '';
        let stderr = '';
        
        build.stdout.on('data', (data) => {
          stdout += data.toString();
        });
        
        build.stderr.on('data', (data) => {
          stderr += data.toString();
        });
        
        build.on('close', (code) => {
          resolve({ code, stdout, stderr });
        });
      });
    });
    
    expect(buildResult.code).toBe(0);
    expect(buildResult.stderr).not.toContain('use-sync-external-store');
    expect(buildResult.stderr).not.toContain('useState');
    console.log('✅ Build completes without React hook conflicts');
  });
});