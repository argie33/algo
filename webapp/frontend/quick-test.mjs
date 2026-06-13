import playwright from "./node_modules/playwright/index.js";
const { chromium } = playwright;
(async () => {
  const b = await chromium.launch({headless:true});
  const p = await b.newPage();
  const e = [];
  p.on("console",m=>m.type()==="error"&&e.push(m.text()));
  p.on("pageerror",err=>e.push(`${err.message}`));
  try {
    console.log("Testing MarketsHealth...");
    await p.goto("http://localhost:5180/app/markets-health",{waitUntil:"load",timeout:10000});
    console.log(e.length?"? "+e[0]:"? MarketsHealth OK");
    e.length=0;
    console.log("Testing Portfolio...");
    await p.goto("http://localhost:5180/app/portfolio",{waitUntil:"load",timeout:10000});
    console.log(e.length?"? "+e[0]:"? Portfolio OK");
  } catch(e){console.error(e.message);} finally{await b.close();}
})();
