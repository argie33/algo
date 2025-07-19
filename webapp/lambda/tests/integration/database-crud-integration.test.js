/**
 * DATABASE CRUD INTEGRATION TESTS
 * Tests all Create, Read, Update, Delete operations with real PostgreSQL
 */

const { Pool } = require('pg')
const database = require('../../utils/database')

describe('Database CRUD Integration Tests', () => {
  let testPool
  let testUserId

  beforeAll(async () => {
    // Initialize test database connection
    testPool = new Pool({
      host: process.env.DB_HOST || 'localhost',
      port: process.env.DB_PORT || 5432,
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || 'password',
      database: process.env.DB_NAME || 'stocks',
      ssl: false,
      max: 3
    })

    // Create test user
    testUserId = `test-user-${Date.now()}`
    await testPool.query(
      'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING',
      [testUserId, 'test@example.com', 'testuser']
    )
  })

  afterAll(async () => {
    // Cleanup test data
    if (testPool) {
      await testPool.query('DELETE FROM portfolios WHERE user_id = $1', [testUserId])
      await testPool.query('DELETE FROM users WHERE id = $1', [testUserId])
      await testPool.end()
    }
  })

  describe('User Management CRUD', () => {
    test('CREATE: Insert new user', async () => {
      const newUserId = `test-user-create-${Date.now()}`
      const result = await testPool.query(
        'INSERT INTO users (id, email, username) VALUES ($1, $2, $3) RETURNING *',
        [newUserId, 'create@test.com', 'createuser']
      )

      expect(result.rows).toHaveLength(1)
      expect(result.rows[0].id).toBe(newUserId)
      expect(result.rows[0].email).toBe('create@test.com')

      // Cleanup
      await testPool.query('DELETE FROM users WHERE id = $1', [newUserId])
    })

    test('READ: Fetch user by ID', async () => {
      const result = await testPool.query(
        'SELECT * FROM users WHERE id = $1',
        [testUserId]
      )

      expect(result.rows).toHaveLength(1)
      expect(result.rows[0].id).toBe(testUserId)
    })

    test('UPDATE: Modify user data', async () => {
      const newEmail = `updated-${Date.now()}@test.com`
      const result = await testPool.query(
        'UPDATE users SET email = $1 WHERE id = $2 RETURNING *',
        [newEmail, testUserId]
      )

      expect(result.rows[0].email).toBe(newEmail)
    })
  })

  describe('Portfolio Management CRUD', () => {
    let testPortfolioId

    test('CREATE: Insert new portfolio', async () => {
      testPortfolioId = `test-portfolio-${Date.now()}`
      const result = await testPool.query(`
        INSERT INTO portfolios (id, user_id, name, total_value, created_at)
        VALUES ($1, $2, $3, $4, NOW())
        RETURNING *
      `, [testPortfolioId, testUserId, 'Test Portfolio', 100000])

      expect(result.rows).toHaveLength(1)
      expect(result.rows[0].name).toBe('Test Portfolio')
      expect(parseFloat(result.rows[0].total_value)).toBe(100000)
    })

    test('READ: Fetch portfolio with holdings', async () => {
      const result = await testPool.query(`
        SELECT p.*, h.symbol, h.shares, h.avg_cost
        FROM portfolios p
        LEFT JOIN holdings h ON p.id = h.portfolio_id
        WHERE p.id = $1
      `, [testPortfolioId])

      expect(result.rows.length).toBeGreaterThan(0)
      expect(result.rows[0].name).toBe('Test Portfolio')
    })

    test('UPDATE: Modify portfolio value', async () => {
      const newValue = 125000
      const result = await testPool.query(`
        UPDATE portfolios
        SET total_value = $1, updated_at = NOW()
        WHERE id = $2
        RETURNING *
      `, [newValue, testPortfolioId])

      expect(parseFloat(result.rows[0].total_value)).toBe(newValue)
    })

    test('DELETE: Remove portfolio', async () => {
      const result = await testPool.query(
        'DELETE FROM portfolios WHERE id = $1 RETURNING *',
        [testPortfolioId]
      )

      expect(result.rows).toHaveLength(1)

      // Verify deletion
      const checkResult = await testPool.query(
        'SELECT * FROM portfolios WHERE id = $1',
        [testPortfolioId]
      )
      expect(checkResult.rows).toHaveLength(0)
    })
  })

  describe('Holdings Management CRUD', () => {
    let portfolioId, holdingId

    beforeAll(async () => {
      portfolioId = `test-portfolio-holdings-${Date.now()}`
      await testPool.query(`
        INSERT INTO portfolios (id, user_id, name, total_value)
        VALUES ($1, $2, 'Holdings Test Portfolio', 50000)
      `, [portfolioId, testUserId])
    })

    afterAll(async () => {
      await testPool.query('DELETE FROM holdings WHERE portfolio_id = $1', [portfolioId])
      await testPool.query('DELETE FROM portfolios WHERE id = $1', [portfolioId])
    })

    test('CREATE: Add holding to portfolio', async () => {
      holdingId = `test-holding-${Date.now()}`
      const result = await testPool.query(`
        INSERT INTO holdings (id, portfolio_id, symbol, shares, avg_cost, current_price)
        VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING *
      `, [holdingId, portfolioId, 'AAPL', 100, 150.00, 155.25])

      expect(result.rows).toHaveLength(1)
      expect(result.rows[0].symbol).toBe('AAPL')
      expect(parseFloat(result.rows[0].shares)).toBe(100)
    })

    test('READ: Fetch holdings for portfolio', async () => {
      const result = await testPool.query(
        'SELECT * FROM holdings WHERE portfolio_id = $1',
        [portfolioId]
      )

      expect(result.rows.length).toBeGreaterThan(0)
      const holding = result.rows.find(h => h.symbol === 'AAPL')
      expect(holding).toBeTruthy()
    })

    test('UPDATE: Modify holding price', async () => {
      const newPrice = 160.00
      const result = await testPool.query(`
        UPDATE holdings
        SET current_price = $1, updated_at = NOW()
        WHERE id = $2
        RETURNING *
      `, [newPrice, holdingId])

      expect(parseFloat(result.rows[0].current_price)).toBe(newPrice)
    })
  })

  describe('Transaction Management CRUD', () => {
    test('CREATE: Record transaction', async () => {
      const transactionId = `test-transaction-${Date.now()}`
      const result = await testPool.query(`
        INSERT INTO transactions (id, user_id, symbol, type, shares, price, executed_at)
        VALUES ($1, $2, $3, $4, $5, $6, NOW())
        RETURNING *
      `, [transactionId, testUserId, 'MSFT', 'BUY', 50, 300.00])

      expect(result.rows).toHaveLength(1)
      expect(result.rows[0].type).toBe('BUY')
      expect(parseFloat(result.rows[0].shares)).toBe(50)

      // Cleanup
      await testPool.query('DELETE FROM transactions WHERE id = $1', [transactionId])
    })

    test('READ: Fetch transaction history', async () => {
      // Create test transaction first
      const transactionId = `test-transaction-history-${Date.now()}`
      await testPool.query(`
        INSERT INTO transactions (id, user_id, symbol, type, shares, price, executed_at)
        VALUES ($1, $2, 'TSLA', 'SELL', 25, 250.00, NOW())
      `, [transactionId, testUserId])

      const result = await testPool.query(`
        SELECT * FROM transactions
        WHERE user_id = $1
        ORDER BY executed_at DESC
        LIMIT 10
      `, [testUserId])

      expect(result.rows.length).toBeGreaterThan(0)
      const transaction = result.rows.find(t => t.id === transactionId)
      expect(transaction.symbol).toBe('TSLA')

      // Cleanup
      await testPool.query('DELETE FROM transactions WHERE id = $1', [transactionId])
    })
  })

  describe('Database Connection Management', () => {
    test('Connection pool handles multiple concurrent queries', async () => {
      const promises = Array.from({ length: 10 }, (_, i) =>
        testPool.query('SELECT $1 as test_value', [`test-${i}`])
      )

      const results = await Promise.all(promises)

      expect(results).toHaveLength(10)
      results.forEach((result, i) => {
        expect(result.rows[0].test_value).toBe(`test-${i}`)
      })
    })

    test('Database handles transaction rollback', async () => {
      const client = await testPool.connect()

      try {
        await client.query('BEGIN')

        const testId = `test-rollback-${Date.now()}`
        await client.query(
          'INSERT INTO users (id, email, username) VALUES ($1, $2, $3)',
          [testId, 'rollback@test.com', 'rollbackuser']
        )

        // Simulate error and rollback
        await client.query('ROLLBACK')

        // Verify user was not created
        const result = await testPool.query('SELECT * FROM users WHERE id = $1', [testId])
        expect(result.rows).toHaveLength(0)
      } finally {
        client.release()
      }
    })

    test('Database handles connection errors gracefully', async () => {
      // Create a pool with invalid configuration
      const badPool = new Pool({
        host: 'nonexistent-host',
        port: 5432,
        user: 'baduser',
        password: 'badpass',
        database: 'baddatabase',
        connectionTimeoutMillis: 1000
      })

      try {
        await badPool.query('SELECT 1')
        expect(false).toBe(true) // Should not reach here
      } catch (error) {
        expect(error).toBeTruthy()
        expect(error.message).toContain('ENOTFOUND')
      } finally {
        await badPool.end()
      }
    })
  })

  describe('Data Integrity and Constraints', () => {
    test('Enforces foreign key constraints', async () => {
      const invalidPortfolioId = 'non-existent-portfolio'

      try {
        await testPool.query(`
          INSERT INTO holdings (id, portfolio_id, symbol, shares, avg_cost)
          VALUES ($1, $2, 'INVALID', 100, 150.00)
        `, [`test-invalid-${Date.now()}`, invalidPortfolioId])

        expect(false).toBe(true) // Should not reach here
      } catch (error) {
        expect(error.message).toContain('foreign key')
      }
    })

    test('Validates data types and constraints', async () => {
      try {
        await testPool.query(`
          INSERT INTO holdings (id, portfolio_id, symbol, shares, avg_cost)
          VALUES ($1, $2, $3, $4, $5)
        `, [`test-invalid-type-${Date.now()}`, testUserId, 'AAPL', 'invalid-number', 150.00])

        expect(false).toBe(true) // Should not reach here
      } catch (error) {
        expect(error.message).toContain('invalid input')
      }
    })
  })
})