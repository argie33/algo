import { chromium } from 'playwright';

async function checkAPIs() {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  const failures = [];
  const successes = [];
  
  page.on('response', response => {
    const url = response.url();
    if (url.includes('/api/')) {
      const status = response.status();
      const key = url.split('?')[0];
      if (status >= 400) {
        failures.push({ url: key, status });
      } else {
        successes.push({ url: key, status });
      }
    }
  });
  
  try {
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(4000);
    
    const unique_failures = [...new Map(failures.map(f => [f.url, f])).values()];
    const unique_successes = [...new Map(successes.map(s => [s.url, s])).values()];
    
    console.log(`✅ API Calls Succeeded (${unique_successes.length}):`);
    unique_successes.slice(0, 10).forEach(s => console.log(`   ${s.status} ${s.url.substring(s.url.indexOf('/api'))}`));
    
    if (unique_failures.length > 0) {
      console.log(`\n❌ API Calls Failed (${unique_failures.length}):`);
      unique_failures.slice(0, 10).forEach(f => console.log(`   ${f.status} ${f.url.substring(f.url.indexOf('/api'))}`));
    }
    
  } finally {
    await browser.close();
  }
}

checkAPIs();
