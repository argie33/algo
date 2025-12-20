import { test, expect } from '@playwright/test';

test('Scores page loads and displays correctly', async ({ page }) => {
  // Navigate to the scores page
  await page.goto('http://localhost:5173/scores', { waitUntil: 'networkidle' });
  
  // Check that page title is correct
  await expect(page).toHaveTitle(/Financial Dashboard/i);
  
  // Check that the page has the main content area
  const rootElement = page.locator('#root');
  await expect(rootElement).toBeVisible();
  
  // Check for page layout - should have header or title indicating scores page
  const pageContent = page.locator('body');
  await expect(pageContent).toBeVisible();
  
  // Verify API endpoint is accessible
  const response = await page.request.get('http://localhost:3001/api/stocks?limit=5');
  expect(response.status()).toBe(200);
  
  const data = await response.json();
  console.log('API Response:', data);
  
  console.log('✅ Scores page loaded successfully!');
});
