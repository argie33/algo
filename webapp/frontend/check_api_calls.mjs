import { chromium } from 'playwright';

async function checkAPICalls() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  const apiErrors = [];
  const apiCalls = [];
  
  // Capture network responses
  page.on('response', response => {
    const status = response.status();
    const url = response.url();
    
    if (!url.includes('localhost') && !url.includes('fonts.googleapis')) return;
    
    apiCalls.push({
      url: url.split('?')[0],
      status: status
    });
    
    if (status >= 400) {
      apiErrors.push({ url, status });
    }
  });
  
  try {
    await page.goto('http://localhost:5174', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(5000);
    
    console.log('=== API Calls Made ===');
    const uniqueCalls = {};
    apiCalls.forEach(c => {
      const key = `${c.url} (${c.status})`;
      uniqueCalls[key] = (uniqueCalls[key] || 0) + 1;
    });
    Object.entries(uniqueCalls).forEach(([k, v]) => {
      console.log(`${k} - called ${v} time(s)`);
    });
    
    if (apiErrors.length > 0) {
      console.log('\n=== API Errors ===');
      apiErrors.forEach(e => console.log(`${e.status}: ${e.url}`));
    }
    
  } finally {
    await browser.close();
  }
}

checkAPICalls();
