import { chromium } from 'playwright';

async function inspectCharts() {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 960 } });
    const page = await context.newPage();

    // Connect to server
    let attempts = 0;
    while (attempts < 10) {
      try {
        await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 10000 });
        break;
      } catch (e) {
        attempts++;
        if (attempts >= 10) throw e;
        await new Promise(r => setTimeout(r, 500));
      }
    }

    await page.waitForTimeout(2000);

    // Inspect Recharts elements
    const rechartsAnalysis = await page.evaluate(() => {
      const charts = document.querySelectorAll('[class*="recharts"]');
      const lineCharts = document.querySelectorAll('svg text, svg line, svg circle');
      
      const issues = [];

      // Check for overlapping text/labels
      lineCharts.forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.width === 0 && rect.height === 0 && el.textContent) {
          issues.push({
            type: 'hidden_element',
            tag: el.tagName,
            content: el.textContent?.slice(0, 30),
            classes: el.getAttribute('class')
          });
        }
      });

      // Check ResponsiveContainer width issue
      const responsiveContainers = document.querySelectorAll('.recharts-responsive-container');
      responsiveContainers.forEach((container, idx) => {
        const svg = container.querySelector('svg');
        const rect = container.getBoundingClientRect();
        if (svg) {
          const svgWidth = svg.getAttribute('width');
          const svgHeight = svg.getAttribute('height');
          if (svgWidth === '-1' || svgHeight === '-1') {
            issues.push({
              type: 'invalid_dimensions',
              containerIdx: idx,
              svgWidth,
              svgHeight,
              containerWidth: Math.round(rect.width),
              containerHeight: Math.round(rect.height)
            });
          }
        }
      });

      // Check axis labels positioning
      const xAxisLabels = document.querySelectorAll('text[class*="tick"]');
      xAxisLabels.forEach((label, idx) => {
        const rect = label.getBoundingClientRect();
        const parent = label.parentElement?.getBoundingClientRect();
        if (parent && rect.width > parent.width * 0.8) {
          issues.push({
            type: 'overlapping_labels',
            axisType: 'x-axis',
            labelIdx: idx,
            labelText: label.textContent,
            labelWidth: Math.round(rect.width),
            parentWidth: Math.round(parent.width)
          });
        }
      });

      // Check dot positioning on lines
      const dots = document.querySelectorAll('circle[class*="dot"]');
      const outOfView = [];
      dots.forEach((dot, idx) => {
        const rect = dot.getBoundingClientRect();
        if (rect.x < 0 || rect.y < 0 || rect.x > window.innerWidth || rect.y > window.innerHeight) {
          if (outOfView.length < 3) {
            outOfView.push({
              dotIdx: idx,
              x: Math.round(rect.x),
              y: Math.round(rect.y),
              r: dot.getAttribute('r')
            });
          }
        }
      });

      if (outOfView.length > 0) {
        issues.push({
          type: 'dots_out_of_view',
          count: outOfView.length,
          samples: outOfView
        });
      }

      return {
        totalCharts: charts.length,
        rechartsContainers: responsiveContainers.length,
        issues: issues.slice(0, 10)
      };
    });

    console.log(JSON.stringify(rechartsAnalysis, null, 2));

    // Navigate to other pages and check
    const pagesToCheck = [
      { url: '/sector-analysis', name: 'sector-analysis' },
      { url: '/trading-signals', name: 'trading-signals' }
    ];

    for (const p of pagesToCheck) {
      try {
        console.log(`\nChecking ${p.url}...`);
        await page.goto(`http://localhost:5173${p.url}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
        await page.waitForTimeout(2000);

        const issues = await page.evaluate(() => {
          const problems = [];
          const svgs = document.querySelectorAll('svg');
          svgs.forEach((svg, idx) => {
            const width = svg.getAttribute('width');
            if (width === '-1') {
              problems.push({ page: 'current', svgIdx: idx, width });
            }
          });
          return problems;
        });

        if (issues.length > 0) {
          console.log(`Found issues: ${JSON.stringify(issues)}`);
        } else {
          console.log('No dimension issues found');
        }
      } catch (e) {
        console.log(`Error on ${p.url}: ${e.message}`);
      }
    }

    await context.close();
  } catch (error) {
    console.error('Fatal error:', error.message);
  } finally {
    if (browser) await browser.close();
  }
}

inspectCharts();
