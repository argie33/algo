import puppeteer from 'puppeteer';

(async () => {
  const browser = await puppeteer.launch({ headless: true });
  const p = await browser.newPage();

  await p.goto('http://localhost:5173/app/scores', { waitUntil: 'networkidle2', timeout: 20000 });
  await new Promise(r => setTimeout(r, 2000));
  
  const text = await p.evaluate(() => document.body.innerText.substring(0, 1500));
  console.log('Stock Scores Page Content:\n');
  console.log(text);

  await p.close();
  await browser.close();
})();
