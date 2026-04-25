import puppeteer from 'puppeteer';

async function checkPageData() {
  let browser;
  try {
    browser = await puppeteer.launch({headless: 'new'});
    const page = await browser.newPage();
    
    await page.goto('http://localhost:5174/', {waitUntil: 'domcontentloaded'}).catch(() => {});
    await new Promise(r => setTimeout(r, 3000));

    const pageData = await page.evaluate(() => {
      return {
        title: document.title,
        url: window.location.href,
        tables: document.querySelectorAll('table').length,
        rows: Array.from(document.querySelectorAll('table tbody tr')).length,
        buttons: document.querySelectorAll('button').length,
        loadingText: !!document.body.innerText.includes('Loading'),
        noDataText: !!document.body.innerText.includes('No data') || !!document.body.innerText.includes('no results'),
        errorText: !!document.body.innerText.match(/error|Error|ERROR/i),
        bodyLength: document.body.innerText.length,
        firstTableContent: document.querySelector('table tbody tr')?.innerText?.substring(0, 100)
      };
    });

    console.log('=== PAGE ANALYSIS ===');
    console.log('Title:', pageData.title);
    console.log('URL:', pageData.url);
    console.log('Tables found:', pageData.tables);
    console.log('Table rows found:', pageData.rows);
    console.log('Buttons found:', pageData.buttons);
    console.log('Page content length:', pageData.bodyLength, 'chars');
    console.log('Shows "Loading":', pageData.loadingText);
    console.log('Shows "No data":', pageData.noDataText);
    console.log('Shows "Error":', pageData.errorText);
    
    if (pageData.rows > 0) {
      console.log('\n✅ DATA IS DISPLAYING');
      console.log('Sample row:', pageData.firstTableContent);
    } else if (pageData.loadingText) {
      console.log('\n⏳ Page still loading...');
    } else if (pageData.noDataText) {
      console.log('\n❌ Page shows "No data" - DATA NOT LOADING');
    } else {
      console.log('\n❓ Page structure unclear');
    }

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    if (browser) await browser.close();
  }
}

checkPageData();
