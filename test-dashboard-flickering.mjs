#!/usr/bin/env node
import { chromium } from 'playwright';
import fs from 'fs';

async function testDashboardFlickering() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    console.log('🔍 Opening dashboard at http://localhost:5175/app...');
    await page.goto('http://localhost:5175/app', { waitUntil: 'domcontentloaded' });

    // Wait a bit for the page to start loading
    await page.waitForTimeout(500);

    console.log('\n📸 Taking screenshot of loading state...');
    const loadingScreenshot = await page.screenshot({ path: 'dashboard-loading.png', fullPage: true });
    console.log('✅ Screenshot saved: dashboard-loading.png');

    // Check for skeleton loaders
    const skeletonCount = await page.locator('[class*="skeleton"]').count();
    console.log(`\n📊 Skeleton loaders detected: ${skeletonCount}`);

    // Wait for the primary data to load (watch for the first real content)
    console.log('\n⏳ Waiting for data to load (max 10 seconds)...');
    await page.waitForTimeout(2000);

    // Take a screenshot of the fully loaded state
    console.log('\n📸 Taking screenshot of loaded dashboard...');
    const loadedScreenshot = await page.screenshot({ path: 'dashboard-loaded.png', fullPage: true });
    console.log('✅ Screenshot saved: dashboard-loaded.png');

    // Wait a bit more and check if any more skeleton loaders appear (signs of flickering)
    console.log('\n🔍 Checking for delayed skeleton loaders (flickering test)...');
    await page.waitForTimeout(1000);

    const finalSkeletonCount = await page.locator('[class*="skeleton"]').count();
    console.log(`📊 Final skeleton loaders: ${finalSkeletonCount}`);

    if (finalSkeletonCount === skeletonCount) {
      console.log('\n✅ NO FLICKERING DETECTED: Skeleton count remained stable');
    } else {
      console.log('\n⚠️  FLICKERING DETECTED: Skeleton count changed after initial load');
    }

    // Now test a refresh
    console.log('\n🔄 Testing refresh behavior...');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(500);

    const refreshSkeletonCount = await page.locator('[class*="skeleton"]').count();
    console.log(`📊 Skeleton loaders after refresh: ${refreshSkeletonCount}`);

    console.log('\n📸 Taking screenshot of refreshed loading state...');
    await page.screenshot({ path: 'dashboard-refresh-loading.png', fullPage: true });
    console.log('✅ Screenshot saved: dashboard-refresh-loading.png');

    // Wait for refresh to complete
    await page.waitForTimeout(3000);

    const refreshLoadedSkeletonCount = await page.locator('[class*="skeleton"]').count();
    console.log(`📊 Skeleton loaders after refresh completes: ${refreshLoadedSkeletonCount}`);

    if (refreshLoadedSkeletonCount === 0) {
      console.log('\n✅ REFRESH TEST PASSED: All skeleton loaders cleared');
    } else {
      console.log(`\n⚠️  REFRESH TEST: Still ${refreshLoadedSkeletonCount} skeleton loaders visible`);
    }

    console.log('\n✅ Dashboard testing complete. Check the screenshots for visual verification.');

  } catch (error) {
    console.error('❌ Error during testing:', error);
  } finally {
    await browser.close();
  }
}

testDashboardFlickering();
