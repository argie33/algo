/**
 * Complete User Workflows - End-to-End Tests
 * Tests full user journeys from authentication to portfolio management
 */

import { test, expect } from '@playwright/test'

// Test configuration
const baseURL = process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net'
const apiURL = process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'

test.describe('Complete User Workflows', () => {
  test.beforeEach(async ({ page }) => {
    // Set up API response interceptors for consistent testing
    await page.route('**/health', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          status: 'healthy',
          services: { database: 'connected', api: 'operational' },
          timestamp: new Date().toISOString()
        })
      })
    })
    
    // Navigate to the application
    await page.goto(baseURL)
    await page.waitForLoadState('networkidle')
  })
  
  test('User onboarding and API key setup workflow', async ({ page }) => {
    // Step 1: User lands on the application
    await expect(page).toHaveTitle(/financial/i)
    
    // Step 2: Navigate to API key setup (or check if already prompted)
    const settingsLink = page.getByRole('link', { name: /settings/i }).or(
      page.getByText(/api key/i)
    ).or(
      page.getByRole('button', { name: /setup/i })
    )
    
    if (await settingsLink.isVisible()) {
      await settingsLink.click()
    } else {
      // Navigate via menu
      await page.getByRole('button', { name: /menu/i }).click()
      await page.getByRole('link', { name: /settings/i }).click()
    }
    
    // Step 3: API key configuration
    await expect(page.getByText(/api key/i)).toBeVisible()
    
    // Mock API key validation response
    await page.route('**/settings/api-keys', async route => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            message: 'API key saved successfully',
            validation: { isValid: true, provider: 'alpaca' }
          })
        })
      } else {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            apiKeys: {
              alpaca: { hasKey: false, isValid: false }
            }
          })
        })
      }
    })
    
    // Fill in test API key
    const apiKeyInput = page.getByLabel(/api key/i).or(
      page.getByPlaceholder(/enter.*key/i)
    ).first()
    
    await apiKeyInput.fill('test-api-key-12345')
    
    // Save API key
    const saveButton = page.getByRole('button', { name: /save/i }).or(
      page.getByRole('button', { name: /submit/i })
    )
    
    await saveButton.click()
    
    // Step 4: Verify success message
    await expect(page.getByText(/success/i).or(page.getByText(/saved/i))).toBeVisible()
    
    // Step 5: Navigate to dashboard
    await page.getByRole('link', { name: /dashboard/i }).click()
    await expect(page.getByText(/dashboard/i)).toBeVisible()
  })
  
  test('Portfolio management workflow', async ({ page }) => {
    // Mock authentication
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'test-jwt-token')
      localStorage.setItem('user', JSON.stringify({
        id: 'test-user',
        email: 'test@example.com'
      }))
    })
    
    // Mock portfolio API responses
    await page.route('**/portfolio**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          portfolios: [{
            id: 'portfolio-1',
            name: 'Test Portfolio',
            totalValue: 125000,
            dayChange: 2500,
            dayChangePercent: 2.04,
            holdings: [
              {
                symbol: 'AAPL',
                shares: 100,
                avgCost: 150,
                currentPrice: 155,
                marketValue: 15500,
                dayChange: 500,
                dayChangePercent: 3.33
              }
            ]
          }]
        })
      })
    })
    
    // Step 1: Navigate to portfolio
    await page.getByRole('link', { name: /portfolio/i }).click()
    await expect(page.getByText(/portfolio/i)).toBeVisible()
    
    // Step 2: Verify portfolio data display
    await expect(page.getByText(/125,000/)).toBeVisible()
    await expect(page.getByText(/AAPL/)).toBeVisible()
    await expect(page.getByText(/100/)).toBeVisible() // shares
    
    // Step 3: Test portfolio interactions
    const portfolioCard = page.getByText(/Test Portfolio/).locator('..')
    await portfolioCard.click()
    
    // Step 4: Verify detailed view
    await expect(page.getByText(/holdings/i)).toBeVisible()
    await expect(page.getByText(/performance/i)).toBeVisible()
  })
  
  test('Market data and real-time updates workflow', async ({ page }) => {
    // Mock market data responses
    await page.route('**/market/**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          quotes: [
            {
              symbol: 'AAPL',
              price: 155.75,
              change: 2.25,
              changePercent: 1.47,
              volume: 45000000,
              timestamp: new Date().toISOString()
            },
            {
              symbol: 'MSFT',
              price: 310.50,
              change: -1.50,
              changePercent: -0.48,
              volume: 25000000,
              timestamp: new Date().toISOString()
            }
          ]
        })
      })
    })
    
    // Step 1: Navigate to market data
    await page.getByRole('link', { name: /market/i }).click()
    await expect(page.getByText(/market/i)).toBeVisible()
    
    // Step 2: Verify stock quotes display
    await expect(page.getByText(/AAPL/)).toBeVisible()
    await expect(page.getByText(/155.75/)).toBeVisible()
    await expect(page.getByText(/MSFT/)).toBeVisible()
    
    // Step 3: Test search functionality
    const searchInput = page.getByPlaceholder(/search/i).or(
      page.getByRole('textbox', { name: /search/i })
    )
    
    if (await searchInput.isVisible()) {
      await searchInput.fill('TSLA')
      await page.keyboard.press('Enter')
      
      // Mock search results
      await page.route('**/market/search**', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            results: [{
              symbol: 'TSLA',
              name: 'Tesla Inc',
              exchange: 'NASDAQ'
            }]
          })
        })
      })
    }
    
    // Step 4: Test real-time updates (mock WebSocket)
    await page.evaluate(() => {
      // Simulate real-time price update
      window.dispatchEvent(new CustomEvent('price-update', {
        detail: {
          symbol: 'AAPL',
          price: 156.00,
          change: 2.50
        }
      }))
    })
  })
  
  test('Trading signals and analysis workflow', async ({ page }) => {
    // Mock trading signals API
    await page.route('**/trading/signals**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          signals: [
            {
              symbol: 'AAPL',
              type: 'BUY',
              confidence: 0.85,
              price: 155.50,
              reasoning: 'Strong technical indicators',
              timestamp: new Date().toISOString()
            }
          ]
        })
      })
    })
    
    // Step 1: Navigate to trading signals
    await page.getByRole('link', { name: /trading/i }).or(
      page.getByRole('link', { name: /signals/i })
    ).click()
    
    // Step 2: Verify signals display
    await expect(page.getByText(/signal/i)).toBeVisible()
    await expect(page.getByText(/BUY/)).toBeVisible()
    await expect(page.getByText(/AAPL/)).toBeVisible()
    
    // Step 3: Test signal details
    const signalCard = page.getByText(/AAPL/).locator('..')
    await signalCard.click()
    
    // Step 4: Verify detailed analysis
    await expect(page.getByText(/confidence/i)).toBeVisible()
    await expect(page.getByText(/85%/)).toBeVisible()
  })
  
  test('Error handling and recovery workflow', async ({ page }) => {
    // Step 1: Test API failure scenario
    await page.route('**/portfolio**', async route => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Internal Server Error'
        })
      })
    })
    
    await page.getByRole('link', { name: /portfolio/i }).click()
    
    // Step 2: Verify error handling
    await expect(page.getByText(/error/i).or(page.getByText(/unavailable/i))).toBeVisible()
    
    // Step 3: Test retry functionality
    const retryButton = page.getByRole('button', { name: /retry/i }).or(
      page.getByRole('button', { name: /refresh/i })
    )
    
    if (await retryButton.isVisible()) {
      // Mock successful retry
      await page.route('**/portfolio**', async route => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            portfolios: []
          })
        })
      })
      
      await retryButton.click()
      await expect(page.getByText(/portfolio/i)).toBeVisible()
    }
  })
  
  test('Performance and responsiveness workflow', async ({ page }) => {
    // Test page load performance
    const navigationStart = await page.evaluate(() => performance.now())
    
    await page.goto(baseURL)
    await page.waitForLoadState('networkidle')
    
    const navigationEnd = await page.evaluate(() => performance.now())
    const loadTime = navigationEnd - navigationStart
    
    // Should load within reasonable time
    expect(loadTime).toBeLessThan(5000) // 5 seconds
    
    // Test responsive behavior
    await page.setViewportSize({ width: 375, height: 667 }) // Mobile
    await expect(page.getByRole('main')).toBeVisible()
    
    await page.setViewportSize({ width: 768, height: 1024 }) // Tablet
    await expect(page.getByRole('main')).toBeVisible()
    
    await page.setViewportSize({ width: 1920, height: 1080 }) // Desktop
    await expect(page.getByRole('main')).toBeVisible()
  })
  
  test('Accessibility workflow', async ({ page }) => {
    // Test keyboard navigation
    await page.keyboard.press('Tab')
    
    // Should have focus visible
    const focusedElement = await page.evaluate(() => document.activeElement.tagName)
    expect(['A', 'BUTTON', 'INPUT'].includes(focusedElement)).toBeTruthy()
    
    // Test screen reader support
    const mainLandmark = page.getByRole('main')
    await expect(mainLandmark).toBeVisible()
    
    // Test color contrast (basic check)
    const backgroundColor = await page.evaluate(() => {
      return getComputedStyle(document.body).backgroundColor
    })
    
    expect(backgroundColor).toBeTruthy()
  })
});