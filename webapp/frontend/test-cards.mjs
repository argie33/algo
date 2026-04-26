import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  await page.goto('http://localhost:5174/app/trading-signals', { waitUntil: 'networkidle' });
  await page.waitForTimeout(1500);
  
  const cardsInfo = await page.evaluate(() => {
    const cards = Array.from(document.querySelectorAll('[class*="card"], [class*="Card"], [role="article"]'));
    
    return cards.slice(0, 5).map(card => ({
      html: card.innerHTML.substring(0, 200),
      text: card.textContent.substring(0, 150),
      hasSignal: card.textContent.includes('Buy') || card.textContent.includes('Sell'),
      classes: card.className
    }));
  });
  
  console.log('Card Contents:');
  cardsInfo.forEach((card, i) => {
    console.log(`\nCard ${i+1}:`);
    console.log(`  Has Buy/Sell: ${card.hasSignal}`);
    console.log(`  Text: ${card.text.substring(0, 100)}`);
  });

  await browser.close();
})();
