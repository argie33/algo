#!/usr/bin/env node

const puppeteer = require('puppeteer');

async function testReactApp() {
  console.log('🧪 Testing React App Rendering Locally...\n');

  let browser;
  try {
    browser = await puppeteer.launch({
      headless: true,
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();

    // Capture console errors
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push(msg.text());
      }
    });

    // Capture page errors
    page.on('pageerror', error => {
      errors.push(`Page Error: ${error.message}`);
    });

    console.log('🌐 Loading http://localhost:3000...');
    await page.goto('http://localhost:3000', { waitUntil: 'networkidle0', timeout: 30000 });

    // Wait for React to potentially load
    await new Promise(resolve => setTimeout(resolve, 3000));

    // Check if root has content
    const rootContent = await page.evaluate(() => {
      const root = document.getElementById('root');
      return {
        hasChildren: root && root.children.length > 0,
        innerHTML: root ? root.innerHTML.substring(0, 200) : 'NO ROOT',
        textContent: root ? root.textContent.substring(0, 100) : 'NO ROOT'
      };
    });

    console.log('🔍 Root Element Analysis:');
    console.log(`   Has Children: ${rootContent.hasChildren}`);
    console.log(`   Text Content: "${rootContent.textContent}"`);

    if (rootContent.hasChildren) {
      console.log('✅ React app appears to be rendering');
    } else {
      console.log('❌ React app NOT rendering (empty root)');
    }

    // Check for specific errors
    console.log('\n🚨 JavaScript Errors Found:');
    if (errors.length === 0) {
      console.log('✅ No JavaScript errors detected');
    } else {
      errors.forEach((error, i) => {
        console.log(`   ${i + 1}. ${error}`);
      });
    }

    // Check for React Context fix working
    const contextFixWorking = await page.evaluate(() => {
      return window.__CONTEXT_FIX_APPLIED__ ||
             document.querySelector('script')?.textContent?.includes('ContextConsumer');
    });

    console.log(`\n🔧 React Context Fix: ${contextFixWorking ? '✅ Active' : '❌ Not Found'}`);

  } catch (error) {
    console.log('❌ Test failed:', error.message);
  } finally {
    if (browser) {
      await browser.close();
    }
  }
}

testReactApp();