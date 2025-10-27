const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  
  await page.goto('http://localhost:5173/sectors', {
    waitUntil: 'networkidle2',
    timeout: 30000
  });
  
  // Wait for both charts to load
  await page.waitForSelector('[class*="MomentumChart"]', { timeout: 5000 }).catch(() => {});
  await page.waitForSelector('svg', { timeout: 5000 });
  
  // Get chart dimensions
  const charts = await page.$$eval('svg', svgs => {
    return svgs.slice(0, 4).map((svg, i) => ({
      index: i,
      width: svg.getBoundingClientRect().width,
      height: svg.getBoundingClientRect().height,
      viewBox: svg.getAttribute('viewBox')
    }));
  });
  
  console.log('Chart dimensions:');
  charts.forEach(c => console.log(`  Chart ${c.index}: ${c.width}x${c.height} (viewBox: ${c.viewBox})`));
  
  // Check legend positioning
  const legends = await page.$$eval('.recharts-legend-wrapper', els => {
    return els.slice(0, 2).map(el => ({
      bottom: el.style.bottom || 'default',
      top: el.style.top || 'default',
      position: el.style.position || 'default'
    }));
  });
  
  console.log('\nLegend positioning:');
  legends.forEach((l, i) => console.log(`  Legend ${i}: bottom=${l.bottom}, top=${l.top}, pos=${l.position}`));
  
  await browser.close();
})();
