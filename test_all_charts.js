const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 3000 });

    console.log('🔍 Testing SectorAnalysis Page - All Charts\n');
    console.log('⏳ Navigating to http://localhost:5173/sectors...');
    await page.goto('http://localhost:5173/sectors', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    console.log('✅ Page loaded\n');

    // Wait for charts to render
    console.log('⏳ Waiting for charts to render...');
    await page.waitForFunction(() => {
      const svgs = document.querySelectorAll('svg');
      return svgs.length >= 5;
    }, { timeout: 10000 });
    await page.evaluate(() => new Promise(resolve => setTimeout(resolve, 2000)));

    // Comprehensive chart analysis
    console.log('📊 CHART ANALYSIS:\n');
    const chartInfo = await page.evaluate(() => {
      const charts = [];

      // Find all LineChart SVGs
      const svgs = Array.from(document.querySelectorAll('svg'));

      svgs.forEach((svg, idx) => {
        const rect = svg.getBoundingClientRect();
        const lines = svg.querySelectorAll('line, polyline, path');

        charts.push({
          index: idx,
          width: Math.round(rect.width),
          height: Math.round(rect.height),
          y: Math.round(rect.y),
          hasLines: lines.length > 0,
          lineCount: lines.length,
          classList: svg.getAttribute('class') || 'svg-recharts'
        });
      });

      return charts;
    });

    // Analyze each chart
    chartInfo.forEach((chart, i) => {
      console.log(`Chart ${i + 1}:`);
      console.log(`  Size: ${chart.width}x${chart.height} at Y=${chart.y}`);
      console.log(`  Lines/Paths: ${chart.lineCount}`);
      console.log(`  Has Data: ${chart.hasLines ? '✅ YES' : '❌ NO'}`);
      console.log();
    });

    // Check for specific legend items
    console.log('🏷️  LEGEND ITEMS:\n');
    const legends = await page.evaluate(() => {
      const items = [];
      const legendTexts = document.querySelectorAll('[class*="legend"] text, .recharts-legend-item text');
      legendTexts.forEach(text => {
        const content = text.textContent?.trim();
        if (content) items.push(content);
      });
      return [...new Set(items)].slice(0, 20);
    });

    legends.forEach(legend => console.log(`  • ${legend}`));

    // Check API data
    console.log('\n📡 API DATA CHECK:\n');
    const apiCheck = await page.evaluate(async () => {
      try {
        const response = await fetch('http://localhost:3001/api/sectors/sectors-with-history');
        const data = await response.json();
        const sectors = data.data?.sectors || [];

        if (sectors.length > 0) {
          const sector = sectors[0];
          const trend = sector.trendData || [];

          return {
            status: '✅ Connected',
            sectors: sectors.length,
            trendRows: trend.length,
            hasMA20: trend.some(r => r.ma_20 !== undefined),
            hasMA50: trend.some(r => r.ma_50 !== undefined),
            hasMA200: trend.some(r => r.ma_200 !== undefined),
            hasRSI: trend.some(r => r.rsi !== undefined),
            sample: trend[0]
          };
        }
      } catch (e) {
        return { status: '❌ Error: ' + e.message };
      }
    });

    console.log(`API Status: ${apiCheck.status}`);
    if (apiCheck.sectors) {
      console.log(`Sectors Loaded: ${apiCheck.sectors}`);
      console.log(`Trend Data Rows: ${apiCheck.trendRows}`);
      console.log(`Has MA20: ${apiCheck.hasMA20 ? '✅' : '❌'}`);
      console.log(`Has MA50: ${apiCheck.hasMA50 ? '✅' : '❌'}`);
      console.log(`Has MA200: ${apiCheck.hasMA200 ? '✅' : '❌'}`);
      console.log(`Has RSI: ${apiCheck.hasRSI ? '✅' : '❌'}`);
    }

    // Take screenshot
    console.log('\n📸 Taking screenshot...');
    const screenshotPath = '/tmp/charts-full-page.png';
    await page.screenshot({ path: screenshotPath, fullPage: true });
    console.log(`✅ Screenshot saved: ${screenshotPath}\n`);

    // Final summary
    console.log('='*50);
    console.log('✅ ALL CHARTS TEST COMPLETE');
    console.log('='*50);
    console.log(`Total SVG Charts Found: ${chartInfo.length}`);
    console.log(`Charts with Data: ${chartInfo.filter(c => c.hasLines).length}`);
    console.log(`API Connected: ${apiCheck.status === '✅ Connected' ? '✅' : '❌'}`);
    console.log(`All Technical Indicators Present: ${apiCheck.hasMA20 && apiCheck.hasMA50 && apiCheck.hasMA200 && apiCheck.hasRSI ? '✅' : '❌'}`);

  } catch (error) {
    console.error('❌ ERROR:', error.message);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
