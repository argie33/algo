const puppeteer = require('puppeteer');
const fs = require('fs');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 2000 });

    console.log('Navigating to http://localhost:5173/sectors...');
    await page.goto('http://localhost:5173/sectors', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    // Wait for charts to render
    console.log('Waiting for charts to render...');
    await page.waitForSelector('svg', { timeout: 10000 });
    await page.waitForFunction(() => {
      const svgs = document.querySelectorAll('svg');
      return svgs.length >= 2;
    }, { timeout: 10000 });

    // Small delay for animation
    await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 1000)));

    // Get chart information
    const chartInfo = await page.evaluate(() => {
      const svgs = Array.from(document.querySelectorAll('svg'));
      return svgs.slice(0, 4).map((svg, i) => {
        const rect = svg.getBoundingClientRect();
        return {
          index: i,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          x: Math.round(rect.x),
          y: Math.round(rect.y),
          viewBox: svg.getAttribute('viewBox')
        };
      });
    });

    console.log('\n=== CHART DIMENSIONS ===');
    chartInfo.forEach(c => {
      console.log(`Chart ${c.index}: ${c.width}x${c.height} at (${c.x}, ${c.y})`);
      console.log(`  viewBox: ${c.viewBox}`);
    });

    // Take full page screenshot
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const screenshotPath = `/tmp/charts-${timestamp}.png`;
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`\n✅ Screenshot saved to ${screenshotPath}`);

    // Compare chart dimensions
    if (chartInfo.length >= 2) {
      const chart0 = chartInfo[0];
      const chart1 = chartInfo[1];

      console.log('\n=== CHART COMPARISON ===');
      console.log(`Chart 0: ${chart0.width}x${chart0.height}`);
      console.log(`Chart 1: ${chart1.width}x${chart1.height}`);

      const sameHeight = chart0.height === chart1.height;
      const sameWidth = chart0.width === chart1.width;

      console.log(`\nHeight Match: ${sameHeight ? '✅' : '❌'}`);
      console.log(`Width Match: ${sameWidth ? '✅' : '❌'}`);

      if (!sameHeight) {
        console.log(`  Difference: ${Math.abs(chart0.height - chart1.height)}px`);
      }
      if (!sameWidth) {
        console.log(`  Difference: ${Math.abs(chart0.width - chart1.width)}px`);
      }
    }

  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
