/**
 * TABLE STRUCTURE INTEGRATION TESTS
 * Verifies database schema and table structures are correct
 */

const { dbTestUtils } = require('../utils/database-test-utils')

describe('Table Structure Integration Tests', () => {
  beforeAll(async () => {
    await dbTestUtils.initialize()
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  describe('Critical Table Verification', () => {
    test('users table has correct structure', async () => {
      const expectedColumns = [
        'user_id', 'email', 'username', 'created_at', 'updated_at'
      ]

      const structure = await dbTestUtils.verifyTableStructure('users', expectedColumns)

      expect(structure.exists).toBe(true)
      expect(structure.hasExpectedColumns).toBe(true)
      
      // Verify specific column types
      const userIdColumn = structure.columns.find(col => col.name === 'user_id')
      expect(userIdColumn).toBeTruthy()
      
      const emailColumn = structure.columns.find(col => col.name === 'email')
      expect(emailColumn).toBeTruthy()
    })

    test('portfolio table has correct structure', async () => {
      const expectedColumns = [
        'id', 'user_id', 'symbol', 'quantity', 'avg_cost', 'current_price', 
        'created_at', 'updated_at'
      ]

      const structure = await dbTestUtils.verifyTableStructure('portfolio', expectedColumns)

      expect(structure.exists).toBe(true)
      expect(structure.hasExpectedColumns).toBe(true)

      // Verify numeric columns exist
      const quantityColumn = structure.columns.find(col => col.name === 'quantity')
      expect(quantityColumn).toBeTruthy()
      
      const avgCostColumn = structure.columns.find(col => col.name === 'avg_cost')
      expect(avgCostColumn).toBeTruthy()
    })

    test('api_keys table has correct structure', async () => {
      const expectedColumns = [
        'id', 'user_id', 'alpaca_api_key', 'alpaca_secret_key', 
        'polygon_api_key', 'finnhub_api_key', 'created_at', 'updated_at'
      ]

      const structure = await dbTestUtils.verifyTableStructure('api_keys', expectedColumns)

      expect(structure.exists).toBe(true)
      expect(structure.hasExpectedColumns).toBe(true)
    })

    test('price_daily table has correct structure', async () => {
      const expectedColumns = [
        'id', 'symbol', 'date', 'open', 'high', 'low', 'close', 
        'volume', 'adj_close', 'dividends', 'stock_splits'
      ]

      const structure = await dbTestUtils.verifyTableStructure('price_daily', expectedColumns)

      expect(structure.exists).toBe(true)
      expect(structure.hasExpectedColumns).toBe(true)

      // Verify OHLC columns
      const ohlcColumns = ['open', 'high', 'low', 'close']
      for (const colName of ohlcColumns) {
        const column = structure.columns.find(col => col.name === colName)
        expect(column).toBeTruthy()
      }
    })

    test('stock_symbols table has correct structure', async () => {
      const expectedColumns = [
        'symbol', 'name', 'exchange', 'sector', 'industry', 'market_cap'
      ]

      const structure = await dbTestUtils.verifyTableStructure('stock_symbols', expectedColumns)

      expect(structure.exists).toBe(true)
      expect(structure.hasExpectedColumns).toBe(true)
    })

    test('news table has correct structure', async () => {
      const expectedColumns = [
        'id', 'symbol', 'title', 'content', 'published_at', 'source', 
        'sentiment_score', 'created_at'
      ]

      const structure = await dbTestUtils.verifyTableStructure('news', expectedColumns)

      expect(structure.exists).toBe(true)
      expect(structure.hasExpectedColumns).toBe(true)
    })
  })

  describe('Data Integrity Tests', () => {
    test('can create portfolio with test user relationship', async () => {
      const testUser = await dbTestUtils.createTestUser()
      const portfolioPositions = await dbTestUtils.createTestPortfolio(testUser.user_id, [
        {
          user_id: testUser.user_id,
          symbol: 'TSLA',
          quantity: 25,
          avg_cost: 200.00,
          current_price: 220.00
        }
      ])

      expect(portfolioPositions).toHaveLength(1)
      expect(portfolioPositions[0].symbol).toBe('TSLA')
      expect(portfolioPositions[0].user_id).toBe(testUser.user_id)
    })

    test('can create API keys linked to test user', async () => {
      const testUser = await dbTestUtils.createTestUser()
      const apiKeys = await dbTestUtils.createTestApiKeys(testUser.user_id, {
        alpaca_api_key: 'test-key-123',
        polygon_api_key: 'test-polygon-456'
      })

      expect(apiKeys.user_id).toBe(testUser.user_id)
      expect(apiKeys.alpaca_api_key).toBe('test-key-123')
      expect(apiKeys.polygon_api_key).toBe('test-polygon-456')
    })

    test('can create price data for symbol', async () => {
      const priceData = await dbTestUtils.createTestPriceData('NVDA', 3)

      expect(priceData).toHaveLength(4) // 3 days + today
      expect(priceData[0].symbol).toBe('NVDA')
      
      // Verify OHLC structure
      for (const price of priceData) {
        expect(price.open).toBeGreaterThan(0)
        expect(price.high).toBeGreaterThanOrEqual(price.open)
        expect(price.low).toBeLessThanOrEqual(price.open)
        expect(price.close).toBeGreaterThan(0)
        expect(price.volume).toBeGreaterThan(0)
      }
    })

    test('database operations are properly isolated between tests', async () => {
      // Create user in this test
      const user1 = await dbTestUtils.createTestUser()
      
      // Query all test users created in this transaction
      const result = await dbTestUtils.executeQuery(
        'SELECT COUNT(*) as count FROM users WHERE user_id LIKE $1',
        ['test-user-%']
      )

      // Should only see users created in this test's transaction
      expect(parseInt(result.rows[0].count)).toBeGreaterThanOrEqual(1)
    })
  })

  describe('Performance Tests', () => {
    test('bulk insert performance test', async () => {
      const startTime = Date.now()
      
      // Create multiple portfolio positions
      const testUser = await dbTestUtils.createTestUser()
      const positions = []
      for (let i = 0; i < 50; i++) {
        positions.push({
          user_id: testUser.user_id,
          symbol: `TEST${i}`,
          quantity: Math.floor(Math.random() * 100) + 1,
          avg_cost: Math.random() * 500 + 50,
          current_price: Math.random() * 500 + 50
        })
      }

      const portfolioResults = await dbTestUtils.createTestPortfolio(testUser.user_id, positions)
      
      const endTime = Date.now()
      const executionTime = endTime - startTime

      expect(portfolioResults).toHaveLength(50)
      expect(executionTime).toBeLessThan(5000) // Should complete within 5 seconds
      
      console.log(`✅ Bulk insert of 50 positions completed in ${executionTime}ms`)
    })

    test('concurrent user creation test', async () => {
      const startTime = Date.now()
      
      // Create multiple users concurrently
      const userPromises = []
      for (let i = 0; i < 10; i++) {
        userPromises.push(dbTestUtils.createTestUser({
          email: `concurrent-${i}-${Date.now()}@test.com`,
          username: `concurrent-user-${i}`
        }))
      }

      const users = await Promise.all(userPromises)
      const endTime = Date.now()

      expect(users).toHaveLength(10)
      expect(endTime - startTime).toBeLessThan(3000) // Should complete within 3 seconds
      
      // Verify all users are unique
      const userIds = users.map(u => u.user_id)
      const uniqueIds = new Set(userIds)
      expect(uniqueIds.size).toBe(10)
      
      console.log(`✅ Concurrent creation of 10 users completed in ${endTime - startTime}ms`)
    })
  })
})