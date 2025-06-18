#!/usr/bin/env python3
"""
Test script for Fear & Greed loader to verify Chrome/browser setup works
"""
import asyncio
import logging
import sys
from pyppeteer import launch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

async def test_browser():
    """Test browser launch and basic functionality"""
    logging.info("Testing browser setup...")
    
    launch_args = [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor',
        '--disable-extensions',
        '--disable-plugins',
        '--no-first-run',
        '--no-default-browser-check',
        '--single-process',
    ]
    
    browser_paths = [
        '/usr/bin/google-chrome-stable',
        '/usr/bin/google-chrome',
        '/usr/bin/chromium-browser',
        '/usr/bin/chromium',
    ]
    
    browser = None
    try:
        # Test each browser path
        for path in browser_paths:
            try:
                logging.info(f"Testing browser at: {path}")
                browser = await launch(
                    args=launch_args,
                    headless=True,
                    executablePath=path
                )
                logging.info(f"✅ Successfully launched browser at {path}")
                
                # Test basic page navigation
                page = await browser.newPage()
                await page.goto('https://httpbin.org/json')
                content = await page.content()
                
                if len(content) > 100:
                    logging.info("✅ Browser can navigate and load pages successfully")
                    await browser.close()
                    return True
                else:
                    logging.warning("⚠️ Page loaded but content seems empty")
                
                await browser.close()
                browser = None
                
            except Exception as e:
                logging.warning(f"❌ Failed to launch browser at {path}: {e}")
                if browser:
                    try:
                        await browser.close()
                    except:
                        pass
                    browser = None
                continue
        
        # Try auto-detection as fallback
        logging.info("Testing pyppeteer auto-detection...")
        browser = await launch(args=launch_args, headless=True)
        logging.info("✅ Pyppeteer auto-detection successful")
        
        page = await browser.newPage()
        await page.goto('https://httpbin.org/json')
        content = await page.content()
        
        if len(content) > 100:
            logging.info("✅ Auto-detected browser works correctly")
            return True
        else:
            logging.error("❌ Auto-detected browser cannot load pages properly")
            return False
            
    except Exception as e:
        logging.error(f"❌ All browser tests failed: {e}")
        return False
    
    finally:
        if browser:
            try:
                await browser.close()
            except:
                pass

async def main():
    """Main test function"""
    logging.info("🧪 Starting Fear & Greed browser compatibility test")
    
    success = await test_browser()
    
    if success:
        logging.info("🎉 Browser test successful - Fear & Greed loader should work!")
        sys.exit(0)
    else:
        logging.error("💥 Browser test failed - Fear & Greed loader will not work")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
