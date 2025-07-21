# Financial Dashboard Test Plan

## Test Strategy Overview

### Testing Pyramid Approach
```
                    /\
                   /  \
                  /    \
                 / E2E  \
                /  Tests \
               /___4____\
              /          \
             / Integration \
            /    Tests     \
           /______30_______\
          /                \
         /   Unit Tests     \
        /       66%         \
       /___________________\
```

### Testing Philosophy
- **Test Early, Test Often** - Continuous testing throughout development lifecycle
- **Quality Gates** - Automated quality checks prevent broken code deployment
- **Risk-Based Testing** - Focus testing efforts on high-risk, high-value features
- **Shift-Left Testing** - Catch defects early in development process
- **Comprehensive Coverage** - Unit, integration, and end-to-end test coverage

## Test Environment Setup

### Development Environment
```javascript
// vitest.config.js - Test configuration
export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      threshold: {
        global: {
          branches: 80,
          functions: 85,
          lines: 90,
          statements: 90
        }
      },
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.d.ts',
        '**/*.config.js'
      ]
    },
    globals: true,
    mockReset: true,
    clearMocks: true
  }
});
```

### Test Data Management
- **Fixtures** - Predefined test data for consistent test scenarios
- **Factories** - Dynamic test data generation for varied scenarios
- **Mock Services** - Simulated external API responses and database states
- **Seed Data** - Controlled database states for integration testing
- **Test Isolation** - Each test runs with clean, isolated state

### CI/CD Integration
```yaml
# GitHub Actions test workflow
name: Test Suite
on: [push, pull_request]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'npm'
      - name: Install dependencies
        run: npm ci
      - name: Run unit tests
        run: npm test -- --coverage --watchAll=false
      - name: Upload coverage reports
        uses: codecov/codecov-action@v3

  integration-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: test_db
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: npm run test:integration
```

## Unit Testing Strategy

### Component Testing Approach
```javascript
// Example: Portfolio component unit test
describe('📊 PortfolioSummary Component', () => {
  const mockPortfolio = {
    totalValue: 125000,
    dayChange: 2500,
    dayChangePercent: 2.04,
    holdings: [
      {
        symbol: 'AAPL',
        quantity: 100,
        currentPrice: 175.50,
        marketValue: 17550,
        gainLoss: 1550,
        gainLossPercent: 9.68
      }
    ]
  };

  beforeEach(() => {
    render(
      <ThemeProvider theme={theme}>
        <PortfolioSummary portfolio={mockPortfolio} />
      </ThemeProvider>
    );
  });

  it('should display portfolio total value correctly', () => {
    expect(screen.getByText('$125,000.00')).toBeInTheDocument();
  });

  it('should show positive gain with green color', () => {
    const gainElement = screen.getByTestId('day-change');
    expect(gainElement).toHaveTextContent('+$2,500.00');
    expect(gainElement).toHaveStyle({ color: 'rgb(46, 125, 50)' });
  });

  it('should handle loading state gracefully', () => {
    render(<PortfolioSummary portfolio={null} loading={true} />);
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument();
  });

  it('should handle error state with proper messaging', () => {
    render(<PortfolioSummary error="Failed to load portfolio" />);
    expect(screen.getByText('Failed to load portfolio')).toBeInTheDocument();
  });
});
```

### Service Layer Testing
```javascript
// Example: API service unit test with comprehensive mocking
describe('🔧 ApiService', () => {
  let apiService;
  
  beforeEach(() => {
    global.fetch = vi.fn();
    apiService = new ApiService();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Portfolio Data Retrieval', () => {
    it('should fetch portfolio data successfully', async () => {
      const mockResponse = {
        success: true,
        data: {
          totalValue: 100000,
          holdings: [
            { symbol: 'AAPL', quantity: 100, currentPrice: 150 }
          ]
        }
      };

      global.fetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: vi.fn().mockResolvedValue(mockResponse)
      });

      const result = await apiService.getPortfolioData('user123');
      
      expect(global.fetch).toHaveBeenCalledWith(
        'https://api.example.com/portfolios/user123',
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Authorization': expect.stringMatching(/^Bearer /)
          })
        })
      );
      
      expect(result).toEqual(mockResponse.data);
    });

    it('should handle network errors with retry logic', async () => {
      global.fetch
        .mockRejectedValueOnce(new Error('Network error'))
        .mockRejectedValueOnce(new Error('Network error'))
        .mockResolvedValueOnce({
          ok: true,
          json: vi.fn().mockResolvedValue({ success: true, data: {} })
        });

      const result = await apiService.getPortfolioData('user123');
      
      expect(global.fetch).toHaveBeenCalledTimes(3);
      expect(result).toBeDefined();
    });

    it('should handle authentication failures', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: vi.fn().mockResolvedValue({ error: 'Unauthorized' })
      });

      await expect(
        apiService.getPortfolioData('user123')
      ).rejects.toThrow('Authentication failed');
    });
  });
});
```

### Hook Testing Strategy
```javascript
// Example: Custom hook testing with comprehensive scenarios
describe('📈 usePortfolioData Hook', () => {
  const mockApiService = {
    getPortfolioData: vi.fn(),
    getMarketData: vi.fn()
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should load portfolio data on mount', async () => {
    mockApiService.getPortfolioData.mockResolvedValue({
      totalValue: 50000,
      holdings: []
    });

    const { result } = renderHook(() => usePortfolioData('user123'));

    expect(result.current.loading).toBe(true);

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.portfolio).toEqual({
      totalValue: 50000,
      holdings: []
    });
    expect(mockApiService.getPortfolioData).toHaveBeenCalledWith('user123');
  });

  it('should handle errors gracefully', async () => {
    mockApiService.getPortfolioData.mockRejectedValue(
      new Error('API service unavailable')
    );

    const { result } = renderHook(() => usePortfolioData('user123'));

    await waitFor(() => {
      expect(result.current.error).toBe('API service unavailable');
    });

    expect(result.current.loading).toBe(false);
    expect(result.current.portfolio).toBeNull();
  });

  it('should refresh data when requested', async () => {
    mockApiService.getPortfolioData
      .mockResolvedValueOnce({ totalValue: 50000 })
      .mockResolvedValueOnce({ totalValue: 52000 });

    const { result } = renderHook(() => usePortfolioData('user123'));

    await waitFor(() => {
      expect(result.current.portfolio.totalValue).toBe(50000);
    });

    act(() => {
      result.current.refresh();
    });

    await waitFor(() => {
      expect(result.current.portfolio.totalValue).toBe(52000);
    });

    expect(mockApiService.getPortfolioData).toHaveBeenCalledTimes(2);
  });
});
```

### Utility Function Testing
```javascript
// Example: Utility function testing with edge cases
describe('🧮 Financial Calculations', () => {
  describe('calculatePortfolioMetrics', () => {
    it('should calculate basic portfolio metrics correctly', () => {
      const holdings = [
        { quantity: 100, currentPrice: 150, averagePrice: 140 },
        { quantity: 50, currentPrice: 200, averagePrice: 180 }
      ];

      const metrics = calculatePortfolioMetrics(holdings);

      expect(metrics.totalValue).toBe(25000); // (100*150) + (50*200)
      expect(metrics.totalCost).toBe(23000);  // (100*140) + (50*180)
      expect(metrics.totalGain).toBe(2000);   // 25000 - 23000
      expect(metrics.totalGainPercent).toBeCloseTo(8.70, 2);
    });

    it('should handle empty holdings array', () => {
      const metrics = calculatePortfolioMetrics([]);

      expect(metrics.totalValue).toBe(0);
      expect(metrics.totalCost).toBe(0);
      expect(metrics.totalGain).toBe(0);
      expect(metrics.totalGainPercent).toBe(0);
    });

    it('should handle invalid data gracefully', () => {
      const holdings = [
        { quantity: null, currentPrice: 150, averagePrice: 140 },
        { quantity: 50, currentPrice: undefined, averagePrice: 180 }
      ];

      expect(() => calculatePortfolioMetrics(holdings)).not.toThrow();
      
      const metrics = calculatePortfolioMetrics(holdings);
      expect(metrics.totalValue).toBe(0);
    });
  });
});
```

## Integration Testing Strategy

### API Integration Testing
```javascript
// Example: Real API integration test with database
describe('🔌 Portfolio API Integration', () => {
  let testDb;
  let server;
  let authToken;

  beforeAll(async () => {
    testDb = await createTestDatabase();
    server = await startTestServer();
    authToken = await createTestUser();
  });

  afterAll(async () => {
    await closeTestServer(server);
    await cleanupTestDatabase(testDb);
  });

  beforeEach(async () => {
    await seedTestData(testDb);
  });

  afterEach(async () => {
    await cleanupTestData(testDb);
  });

  describe('GET /api/portfolios', () => {
    it('should return user portfolios with correct structure', async () => {
      const response = await request(server)
        .get('/api/portfolios')
        .set('Authorization', `Bearer ${authToken}`)
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.arrayContaining([
          expect.objectContaining({
            id: expect.any(String),
            name: expect.any(String),
            totalValue: expect.any(Number),
            holdings: expect.any(Array)
          })
        ])
      });
    });

    it('should handle unauthorized requests', async () => {
      const response = await request(server)
        .get('/api/portfolios')
        .expect(401);

      expect(response.body.error.code).toBe('UNAUTHORIZED');
    });

    it('should filter portfolios by user ownership', async () => {
      const otherUserToken = await createTestUser({ email: 'other@test.com' });
      
      const response1 = await request(server)
        .get('/api/portfolios')
        .set('Authorization', `Bearer ${authToken}`)
        .expect(200);

      const response2 = await request(server)
        .get('/api/portfolios')
        .set('Authorization', `Bearer ${otherUserToken}`)
        .expect(200);

      expect(response1.body.data).toHaveLength(1);
      expect(response2.body.data).toHaveLength(0);
    });
  });

  describe('POST /api/portfolios', () => {
    it('should create new portfolio successfully', async () => {
      const portfolioData = {
        name: 'Test Portfolio',
        description: 'Integration test portfolio'
      };

      const response = await request(server)
        .post('/api/portfolios')
        .set('Authorization', `Bearer ${authToken}`)
        .send(portfolioData)
        .expect(201);

      expect(response.body.data).toMatchObject({
        name: 'Test Portfolio',
        description: 'Integration test portfolio',
        totalValue: 0,
        holdings: []
      });

      // Verify database persistence
      const dbPortfolio = await testDb.portfolio.findUnique({
        where: { id: response.body.data.id }
      });
      expect(dbPortfolio).toBeTruthy();
    });

    it('should validate required fields', async () => {
      const response = await request(server)
        .post('/api/portfolios')
        .set('Authorization', `Bearer ${authToken}`)
        .send({})
        .expect(400);

      expect(response.body.error.code).toBe('VALIDATION_ERROR');
      expect(response.body.error.details).toContainEqual(
        expect.objectContaining({
          field: 'name',
          message: 'Portfolio name is required'
        })
      );
    });
  });
});
```

### Database Integration Testing
```javascript
// Example: Database layer integration testing
describe('💾 Database Operations', () => {
  let prisma;

  beforeAll(async () => {
    prisma = new PrismaClient({
      datasources: { db: { url: process.env.TEST_DATABASE_URL } }
    });
    await prisma.$connect();
  });

  afterAll(async () => {
    await prisma.$disconnect();
  });

  beforeEach(async () => {
    await cleanupDatabase(prisma);
  });

  describe('User Portfolio Relationships', () => {
    it('should maintain referential integrity', async () => {
      const user = await prisma.user.create({
        data: {
          email: 'test@example.com',
          passwordHash: 'hashed_password'
        }
      });

      const portfolio = await prisma.portfolio.create({
        data: {
          name: 'Test Portfolio',
          userId: user.id
        }
      });

      const holding = await prisma.holding.create({
        data: {
          symbol: 'AAPL',
          quantity: 100,
          averagePrice: 150,
          portfolioId: portfolio.id
        }
      });

      // Test cascade delete
      await prisma.user.delete({ where: { id: user.id } });

      const deletedPortfolio = await prisma.portfolio.findUnique({
        where: { id: portfolio.id }
      });
      const deletedHolding = await prisma.holding.findUnique({
        where: { id: holding.id }
      });

      expect(deletedPortfolio).toBeNull();
      expect(deletedHolding).toBeNull();
    });

    it('should handle concurrent updates correctly', async () => {
      const user = await prisma.user.create({
        data: { email: 'test@example.com', passwordHash: 'hash' }
      });

      const portfolio = await prisma.portfolio.create({
        data: { name: 'Test Portfolio', userId: user.id }
      });

      // Simulate concurrent updates
      const updates = Array.from({ length: 10 }, (_, i) =>
        prisma.portfolio.update({
          where: { id: portfolio.id },
          data: { name: `Updated Portfolio ${i}` }
        })
      );

      await Promise.allSettled(updates);

      const finalPortfolio = await prisma.portfolio.findUnique({
        where: { id: portfolio.id }
      });

      expect(finalPortfolio.name).toMatch(/Updated Portfolio \d/);
    });
  });
});
```

### External Service Integration Testing
```javascript
// Example: External API integration testing with circuit breaker
describe('🌐 External Service Integration', () => {
  let mockServer;
  
  beforeAll(() => {
    mockServer = setupServer(
      rest.get('https://api.alpaca.markets/v2/account', (req, res, ctx) => {
        return res(ctx.json({
          id: 'test-account-id',
          status: 'ACTIVE',
          buying_power: '100000'
        }));
      }),
      
      rest.get('https://api.alpaca.markets/v2/positions', (req, res, ctx) => {
        return res(ctx.json([
          {
            symbol: 'AAPL',
            qty: '100',
            market_value: '15000',
            unrealized_pl: '1000'
          }
        ]));
      })
    );
    mockServer.listen();
  });

  afterAll(() => {
    mockServer.close();
  });

  afterEach(() => {
    mockServer.resetHandlers();
  });

  describe('Alpaca API Integration', () => {
    it('should fetch account information successfully', async () => {
      const alpacaService = new AlpacaService({
        apiKey: 'test-key',
        secretKey: 'test-secret',
        baseUrl: 'https://api.alpaca.markets'
      });

      const account = await alpacaService.getAccountInfo();

      expect(account).toMatchObject({
        id: 'test-account-id',
        status: 'ACTIVE',
        buyingPower: 100000
      });
    });

    it('should handle API rate limiting', async () => {
      mockServer.use(
        rest.get('https://api.alpaca.markets/v2/account', (req, res, ctx) => {
          return res(
            ctx.status(429),
            ctx.json({ message: 'Rate limit exceeded' })
          );
        })
      );

      const alpacaService = new AlpacaService({
        apiKey: 'test-key',
        secretKey: 'test-secret'
      });

      await expect(
        alpacaService.getAccountInfo()
      ).rejects.toThrow('Rate limit exceeded');
      
      // Verify retry logic was triggered
      expect(alpacaService.circuitBreaker.stats.failures).toBeGreaterThan(0);
    });

    it('should implement circuit breaker for service failures', async () => {
      mockServer.use(
        rest.get('https://api.alpaca.markets/v2/account', (req, res, ctx) => {
          return res.networkError('Service unavailable');
        })
      );

      const alpacaService = new AlpacaService({
        apiKey: 'test-key',
        secretKey: 'test-secret'
      });

      // Trigger circuit breaker
      for (let i = 0; i < 5; i++) {
        try {
          await alpacaService.getAccountInfo();
        } catch (error) {
          // Expected to fail
        }
      }

      expect(alpacaService.circuitBreaker.opened).toBe(true);
      
      // Subsequent calls should fail fast
      const start = Date.now();
      try {
        await alpacaService.getAccountInfo();
      } catch (error) {
        const duration = Date.now() - start;
        expect(duration).toBeLessThan(100); // Should fail quickly
      }
    });
  });
});
```

## End-to-End Testing Strategy

### User Journey Testing
```javascript
// Example: Complete user workflow E2E test
describe('🎭 User Journey: Portfolio Management', () => {
  beforeEach(async () => {
    // Setup test environment
    await page.goto('http://localhost:3000');
    await setupTestDatabase();
  });

  afterEach(async () => {
    await cleanupTestDatabase();
  });

  test('User can create and manage a complete portfolio', async () => {
    // Step 1: User registration and login
    await page.click('[data-testid="register-button"]');
    await page.fill('[data-testid="email-input"]', 'test@example.com');
    await page.fill('[data-testid="password-input"]', 'SecurePassword123!');
    await page.fill('[data-testid="confirm-password-input"]', 'SecurePassword123!');
    await page.click('[data-testid="create-account-button"]');
    
    await expect(page).toHaveURL('/dashboard');
    await expect(page.locator('[data-testid="welcome-message"]')).toBeVisible();

    // Step 2: API Key Setup
    await page.click('[data-testid="setup-api-keys-button"]');
    await page.selectOption('[data-testid="broker-select"]', 'alpaca');
    await page.fill('[data-testid="api-key-input"]', 'test-api-key');
    await page.fill('[data-testid="secret-key-input"]', 'test-secret-key');
    await page.click('[data-testid="save-api-keys-button"]');
    
    await expect(page.locator('[data-testid="api-status-connected"]')).toBeVisible();

    // Step 3: Create Portfolio
    await page.click('[data-testid="create-portfolio-button"]');
    await page.fill('[data-testid="portfolio-name-input"]', 'My Test Portfolio');
    await page.fill('[data-testid="portfolio-description-input"]', 'E2E test portfolio');
    await page.click('[data-testid="create-portfolio-confirm"]');
    
    await expect(page.locator('text=My Test Portfolio')).toBeVisible();

    // Step 4: Add Holdings
    await page.click('[data-testid="add-holding-button"]');
    await page.fill('[data-testid="symbol-input"]', 'AAPL');
    await page.fill('[data-testid="quantity-input"]', '100');
    await page.fill('[data-testid="price-input"]', '150.00');
    await page.click('[data-testid="save-holding-button"]');
    
    await expect(page.locator('[data-testid="holdings-table"]')).toContainText('AAPL');
    await expect(page.locator('[data-testid="total-value"]')).toContainText('$15,000.00');

    // Step 5: Import Additional Holdings
    await page.click('[data-testid="import-from-broker-button"]');
    await page.selectOption('[data-testid="import-broker-select"]', 'alpaca');
    await page.click('[data-testid="start-import-button"]');
    
    await expect(page.locator('[data-testid="import-progress"]')).toBeVisible();
    await page.waitForSelector('[data-testid="import-complete"]', { timeout: 10000 });
    
    await expect(page.locator('[data-testid="holdings-count"]')).toContainText('5 holdings');

    // Step 6: Verify Analytics
    await page.click('[data-testid="analytics-tab"]');
    await expect(page.locator('[data-testid="allocation-chart"]')).toBeVisible();
    await expect(page.locator('[data-testid="performance-chart"]')).toBeVisible();
    await expect(page.locator('[data-testid="risk-metrics"]')).toBeVisible();

    // Step 7: Portfolio Actions
    await page.click('[data-testid="portfolio-actions-menu"]');
    await page.click('[data-testid="export-portfolio-button"]');
    
    const downloadPromise = page.waitForEvent('download');
    await page.click('[data-testid="export-csv-button"]');
    const download = await downloadPromise;
    
    expect(download.suggestedFilename()).toContain('portfolio-');
    expect(download.suggestedFilename()).toContain('.csv');
  });

  test('User can handle trading operations', async () => {
    await loginTestUser();
    await setupPortfolioWithHoldings();

    // Place a buy order
    await page.click('[data-testid="trading-tab"]');
    await page.click('[data-testid="place-order-button"]');
    
    await page.selectOption('[data-testid="order-type-select"]', 'market');
    await page.selectOption('[data-testid="order-side-select"]', 'buy');
    await page.fill('[data-testid="order-symbol-input"]', 'MSFT');
    await page.fill('[data-testid="order-quantity-input"]', '50');
    
    await page.click('[data-testid="review-order-button"]');
    await expect(page.locator('[data-testid="order-confirmation"]')).toBeVisible();
    
    await page.click('[data-testid="confirm-order-button"]');
    await expect(page.locator('[data-testid="order-success"]')).toBeVisible();
    
    // Verify order appears in history
    await page.click('[data-testid="order-history-tab"]');
    await expect(page.locator('[data-testid="recent-orders"]')).toContainText('MSFT');
    await expect(page.locator('[data-testid="recent-orders"]')).toContainText('BUY');
    await expect(page.locator('[data-testid="recent-orders"]')).toContainText('50');
  });
});
```

### Cross-Browser Compatibility Testing
```javascript
// Example: Multi-browser E2E testing configuration
const { devices } = require('@playwright/test');

module.exports = {
  testDir: './e2e',
  timeout: 30000,
  expect: { timeout: 5000 },
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] }
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] }
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] }
    },
    {
      name: 'mobile-chrome',
      use: { ...devices['Pixel 5'] }
    },
    {
      name: 'mobile-safari',
      use: { ...devices['iPhone 13'] }
    }
  ],

  webServer: {
    command: 'npm run start',
    port: 3000,
    reuseExistingServer: !process.env.CI
  }
};
```

## Performance Testing Strategy

### Load Testing Scenarios
```javascript
// Example: K6 load testing script
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';

const errorRate = new Rate('errors');

export let options = {
  stages: [
    { duration: '2m', target: 10 },   // Ramp up to 10 users
    { duration: '5m', target: 10 },   // Stay at 10 users
    { duration: '2m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 50 },   // Stay at 50 users
    { duration: '2m', target: 100 },  // Ramp up to 100 users
    { duration: '5m', target: 100 },  // Stay at 100 users
    { duration: '5m', target: 0 },    // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'], // 95% of requests under 2s
    http_req_failed: ['rate<0.1'],     // Error rate under 10%
    errors: ['rate<0.1']
  }
};

export function setup() {
  // Login and get auth token
  const loginResponse = http.post('http://localhost:3000/api/auth/login', {
    email: 'loadtest@example.com',
    password: 'LoadTest123!'
  });
  
  return { authToken: loginResponse.json('token') };
}

export default function(data) {
  const headers = {
    'Authorization': `Bearer ${data.authToken}`,
    'Content-Type': 'application/json'
  };

  // Test portfolio data retrieval
  const portfolioResponse = http.get(
    'http://localhost:3000/api/portfolios',
    { headers }
  );
  
  const portfolioCheck = check(portfolioResponse, {
    'portfolio status is 200': (r) => r.status === 200,
    'portfolio response time < 1000ms': (r) => r.timings.duration < 1000,
    'portfolio has data': (r) => r.json('data').length > 0
  });
  
  errorRate.add(!portfolioCheck);

  // Test market data retrieval
  const marketResponse = http.get(
    'http://localhost:3000/api/market/quote/AAPL',
    { headers }
  );
  
  const marketCheck = check(marketResponse, {
    'market status is 200': (r) => r.status === 200,
    'market response time < 500ms': (r) => r.timings.duration < 500,
    'market has price data': (r) => r.json('data.price') !== undefined
  });
  
  errorRate.add(!marketCheck);

  sleep(1);
}

export function teardown(data) {
  // Cleanup test data if needed
  http.post('http://localhost:3000/api/test/cleanup', {}, {
    headers: { 'Authorization': `Bearer ${data.authToken}` }
  });
}
```

### Frontend Performance Testing
```javascript
// Example: Lighthouse CI performance testing
module.exports = {
  ci: {
    collect: {
      url: [
        'http://localhost:3000/',
        'http://localhost:3000/dashboard',
        'http://localhost:3000/portfolio',
        'http://localhost:3000/trading'
      ],
      numberOfRuns: 3
    },
    assert: {
      assertions: {
        'categories:performance': ['warn', { minScore: 0.9 }],
        'categories:accessibility': ['error', { minScore: 0.9 }],
        'categories:best-practices': ['warn', { minScore: 0.9 }],
        'categories:seo': ['warn', { minScore: 0.9 }],
        'first-contentful-paint': ['warn', { maxNumericValue: 2000 }],
        'largest-contentful-paint': ['error', { maxNumericValue: 4000 }],
        'cumulative-layout-shift': ['error', { maxNumericValue: 0.1 }]
      }
    },
    upload: {
      target: 'temporary-public-storage'
    }
  }
};
```

## Security Testing Strategy

### Authentication & Authorization Testing
```javascript
// Example: Security-focused integration tests
describe('🔒 Security Testing', () => {
  describe('Authentication Security', () => {
    test('should prevent SQL injection in login', async () => {
      const maliciousPayload = {
        email: "admin@test.com'; DROP TABLE users; --",
        password: 'password'
      };

      const response = await request(app)
        .post('/api/auth/login')
        .send(maliciousPayload)
        .expect(400);

      expect(response.body.error.code).toBe('VALIDATION_ERROR');
      
      // Verify database integrity
      const userCount = await prisma.user.count();
      expect(userCount).toBeGreaterThan(0);
    });

    test('should enforce rate limiting on login attempts', async () => {
      const loginData = {
        email: 'test@example.com',
        password: 'wrongpassword'
      };

      // Make multiple failed login attempts
      const requests = Array.from({ length: 10 }, () =>
        request(app)
          .post('/api/auth/login')
          .send(loginData)
      );

      const responses = await Promise.all(requests);
      const rateLimitedResponses = responses.filter(r => r.status === 429);
      
      expect(rateLimitedResponses.length).toBeGreaterThan(0);
    });

    test('should validate JWT token integrity', async () => {
      const tamperedToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c';

      const response = await request(app)
        .get('/api/portfolios')
        .set('Authorization', `Bearer ${tamperedToken}`)
        .expect(401);

      expect(response.body.error.code).toBe('INVALID_TOKEN');
    });
  });

  describe('Input Validation Security', () => {
    test('should sanitize XSS attempts in portfolio names', async () => {
      const xssPayload = {
        name: '<script>alert("XSS")</script>Portfolio',
        description: 'Test portfolio'
      };

      const authToken = await getTestAuthToken();
      const response = await request(app)
        .post('/api/portfolios')
        .set('Authorization', `Bearer ${authToken}`)
        .send(xssPayload)
        .expect(201);

      expect(response.body.data.name).not.toContain('<script>');
      expect(response.body.data.name).toBe('Portfolio');
    });

    test('should validate numeric inputs for financial data', async () => {
      const invalidData = {
        symbol: 'AAPL',
        quantity: 'not-a-number',
        price: -100 // Negative price should be invalid
      };

      const authToken = await getTestAuthToken();
      const portfolioId = await createTestPortfolio();

      const response = await request(app)
        .post(`/api/portfolios/${portfolioId}/holdings`)
        .set('Authorization', `Bearer ${authToken}`)
        .send(invalidData)
        .expect(400);

      expect(response.body.error.details).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ field: 'quantity' }),
          expect.objectContaining({ field: 'price' })
        ])
      );
    });
  });

  describe('Data Access Security', () => {
    test('should prevent cross-user data access', async () => {
      const user1Token = await createTestUser('user1@test.com');
      const user2Token = await createTestUser('user2@test.com');

      const user1Portfolio = await createPortfolio(user1Token, 'User 1 Portfolio');

      // User 2 tries to access User 1's portfolio
      const response = await request(app)
        .get(`/api/portfolios/${user1Portfolio.id}`)
        .set('Authorization', `Bearer ${user2Token}`)
        .expect(403);

      expect(response.body.error.code).toBe('FORBIDDEN');
    });

    test('should enforce API key isolation between users', async () => {
      const user1Token = await createTestUser('user1@test.com');
      const user2Token = await createTestUser('user2@test.com');

      await createApiKey(user1Token, 'alpaca', 'user1-key');

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${user2Token}`)
        .expect(200);

      expect(response.body.data).toHaveLength(0);
    });
  });
});
```

## Test Data Management

### Test Fixtures and Factories
```javascript
// Example: Test data factory for consistent test scenarios
class TestDataFactory {
  static createUser(overrides = {}) {
    return {
      id: faker.datatype.uuid(),
      email: faker.internet.email(),
      firstName: faker.name.firstName(),
      lastName: faker.name.lastName(),
      passwordHash: '$2b$12$hash', // Consistent test hash
      createdAt: new Date(),
      preferences: {
        theme: 'light',
        currency: 'USD',
        notifications: true
      },
      ...overrides
    };
  }

  static createPortfolio(userId, overrides = {}) {
    return {
      id: faker.datatype.uuid(),
      userId,
      name: faker.company.companyName() + ' Portfolio',
      description: faker.lorem.sentence(),
      currency: 'USD',
      isDefault: false,
      totalValue: parseFloat(faker.finance.amount(10000, 1000000, 2)),
      createdAt: new Date(),
      ...overrides
    };
  }

  static createHolding(portfolioId, overrides = {}) {
    const symbol = overrides.symbol || faker.helpers.arrayElement([
      'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META', 'NFLX'
    ]);
    
    const quantity = parseFloat(faker.finance.amount(1, 1000, 0));
    const averagePrice = parseFloat(faker.finance.amount(10, 500, 2));
    const currentPrice = averagePrice * (0.8 + Math.random() * 0.4); // ±20%

    return {
      id: faker.datatype.uuid(),
      portfolioId,
      symbol,
      quantity,
      averagePrice,
      currentPrice,
      marketValue: quantity * currentPrice,
      gainLoss: quantity * (currentPrice - averagePrice),
      gainLossPercent: ((currentPrice - averagePrice) / averagePrice) * 100,
      lastUpdated: new Date(),
      ...overrides
    };
  }

  static createMarketData(symbol, overrides = {}) {
    const basePrice = parseFloat(faker.finance.amount(10, 500, 2));
    
    return {
      symbol,
      price: basePrice,
      change: parseFloat(faker.finance.amount(-20, 20, 2)),
      changePercent: parseFloat(faker.finance.amount(-5, 5, 2)),
      volume: parseInt(faker.finance.amount(100000, 10000000, 0)),
      marketCap: parseInt(faker.finance.amount(1000000000, 2000000000000, 0)),
      peRatio: parseFloat(faker.finance.amount(5, 50, 1)),
      timestamp: new Date(),
      ...overrides
    };
  }

  // Create complete test scenario with related data
  static async createCompletePortfolioScenario() {
    const user = this.createUser();
    const portfolio = this.createPortfolio(user.id);
    const holdings = [
      this.createHolding(portfolio.id, { symbol: 'AAPL' }),
      this.createHolding(portfolio.id, { symbol: 'GOOGL' }),
      this.createHolding(portfolio.id, { symbol: 'MSFT' })
    ];

    return {
      user,
      portfolio: {
        ...portfolio,
        holdings,
        totalValue: holdings.reduce((sum, h) => sum + h.marketValue, 0)
      },
      marketData: holdings.map(h => this.createMarketData(h.symbol))
    };
  }
}
```

### Database Seeding and Cleanup
```javascript
// Example: Database setup and teardown utilities
class TestDatabaseManager {
  constructor(prisma) {
    this.prisma = prisma;
  }

  async seedTestData() {
    // Create test users
    const testUsers = await Promise.all([
      this.prisma.user.create({
        data: TestDataFactory.createUser({
          email: 'test@example.com'
        })
      }),
      this.prisma.user.create({
        data: TestDataFactory.createUser({
          email: 'demo@example.com'
        })
      })
    ]);

    // Create test portfolios and holdings
    const testPortfolios = [];
    for (const user of testUsers) {
      const portfolio = await this.prisma.portfolio.create({
        data: TestDataFactory.createPortfolio(user.id)
      });

      const holdings = await Promise.all([
        this.prisma.holding.create({
          data: TestDataFactory.createHolding(portfolio.id, { symbol: 'AAPL' })
        }),
        this.prisma.holding.create({
          data: TestDataFactory.createHolding(portfolio.id, { symbol: 'GOOGL' })
        })
      ]);

      testPortfolios.push({ ...portfolio, holdings });
    }

    return { users: testUsers, portfolios: testPortfolios };
  }

  async cleanupTestData() {
    // Clean up in dependency order
    await this.prisma.holding.deleteMany({});
    await this.prisma.portfolio.deleteMany({});
    await this.prisma.apiKey.deleteMany({});
    await this.prisma.user.deleteMany({});
  }

  async resetDatabase() {
    await this.cleanupTestData();
    await this.seedTestData();
  }

  async createIsolatedTestData(testName) {
    const namespace = `test_${testName}_${Date.now()}`;
    
    return this.seedTestData(namespace);
  }
}
```

## Test Reporting and Metrics

### Coverage Reporting
```javascript
// Example: Comprehensive test coverage configuration
module.exports = {
  collectCoverage: true,
  coverageDirectory: 'coverage',
  coverageReporters: [
    'text',
    'text-summary',
    'html',
    'json',
    'lcov',
    'cobertura'
  ],
  coverageThreshold: {
    global: {
      branches: 80,
      functions: 85,
      lines: 90,
      statements: 90
    },
    './src/services/': {
      branches: 90,
      functions: 95,
      lines: 95,
      statements: 95
    },
    './src/components/': {
      branches: 75,
      functions: 80,
      lines: 85,
      statements: 85
    }
  },
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/test/**',
    '!src/**/*.test.{js,jsx,ts,tsx}',
    '!src/**/*.stories.{js,jsx,ts,tsx}',
    '!src/index.js',
    '!src/serviceWorker.js'
  ]
};
```

### Test Result Analysis
```javascript
// Example: Custom test result aggregation and analysis
class TestResultAnalyzer {
  constructor(testResults) {
    this.results = testResults;
  }

  generateSummaryReport() {
    const summary = {
      totalTests: this.results.numTotalTests,
      passedTests: this.results.numPassedTests,
      failedTests: this.results.numFailedTests,
      pendingTests: this.results.numPendingTests,
      testSuites: this.results.numTotalTestSuites,
      coverage: this.results.coverageMap,
      duration: this.results.testTime,
      performance: {
        slowestTests: this.getSlowTests(),
        averageTestTime: this.getAverageTestTime(),
        flakySuites: this.getFlakySuites()
      }
    };

    return summary;
  }

  getSlowTests(threshold = 5000) {
    return this.results.testResults
      .flatMap(suite => suite.assertionResults)
      .filter(test => test.duration > threshold)
      .sort((a, b) => b.duration - a.duration)
      .slice(0, 10);
  }

  getFlakySuites() {
    return this.results.testResults
      .filter(suite => suite.numFailingTests > 0 && suite.numPassingTests > 0)
      .map(suite => ({
        suiteName: suite.testFilePath,
        passRate: suite.numPassingTests / (suite.numPassingTests + suite.numFailingTests),
        failures: suite.assertionResults.filter(test => test.status === 'failed')
      }));
  }

  generateTrendAnalysis(historicalData) {
    const trends = {
      coverageTrend: this.calculateCoverageTrend(historicalData),
      performanceTrend: this.calculatePerformanceTrend(historicalData),
      stabilityTrend: this.calculateStabilityTrend(historicalData)
    };

    return trends;
  }
}
```

This comprehensive test plan provides the foundation for maintaining high quality and reliability in the financial dashboard application through systematic testing at all levels of the application stack.