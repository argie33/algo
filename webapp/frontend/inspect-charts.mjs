import { chromium } from 'playwright';

async function inspectCharts() {
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      args: ['--disable-blink-features=AutomationControlled']
    });

    const context = await browser.newContext({
      viewport: { width: 1280, height: 960 },
      ignoreHTTPSErrors: true,
    });

    const page = await context.newPage();

    // Wait for server with retries
    let attempts = 0;
    while (attempts < 10) {
      try {
        await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 10000 });
        break;
      } catch (e) {
        attempts++;
        if (attempts >= 10) throw e;
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    console.log('Connected to localhost:5173');
    await page.waitForTimeout(2000);

    const chartsInfo = await page.evaluate(() => {
      const svgs = document.querySelectorAll('svg');
      return {
        totalSvgs: svgs.length,
        svgDetails: Array.from(svgs).slice(0, 5).map((svg, idx) => {
          const rect = svg.getBoundingClientRect();
          return {
            index: idx,
            width: svg.getAttribute('width') || 'auto',
            height: svg.getAttribute('height') || 'auto', 
            viewBox: svg.getAttribute('viewBox'),
            displayWidth: Math.round(rect.width),
            displayHeight: Math.round(rect.height)
          };
        })
      };
    });

    console.log(JSON.stringify(chartsInfo, null, 2));

    await page.screenshot({ path: 'C:\\Users\\arger\\Downloads\\chart-dashboard.png' });
    console.log('Screenshot saved');

    await context.close();
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  } finally {
    if (browser) await browser.close();
  }
}

inspectCharts();
