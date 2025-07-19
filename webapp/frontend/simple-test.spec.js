import { test, expect } from '@playwright/test';

test('simple test', async ({ page }) => {
  await page.goto('https://google.com');
  const title = await page.title();
  expect(title).toBeTruthy();
  console.log('Test passed!');
});