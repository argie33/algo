const alpacaService = require('../../../utils/alpacaService');

describe('Alpaca Integration Service', () => {
  let testDatabase;

  beforeAll(async () => {
    testDatabase = global.TEST_DATABASE;
    
    // Create test tables
    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        provider VARCHAR(50) NOT NULL,
        encrypted_data TEXT NOT NULL,
        salt VARCHAR(255) NOT NULL,
        iv VARCHAR(255) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
      );
    `);

    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS user_portfolios (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        alpaca_account_id VARCHAR(255),
        account_status VARCHAR(50),
        buying_power DECIMAL(15, 2),
        portfolio_value DECIMAL(15, 2),
        day_trade_count INTEGER DEFAULT 0,
        last_synced TIMESTAMP WITH TIME ZONE DEFAULT NOW()
      );
    `);

    await testDatabase.query(`
      CREATE TABLE IF NOT EXISTS positions (
        id SERIAL PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        symbol VARCHAR(10) NOT NULL,
        quantity DECIMAL(15, 8) NOT NULL,
        market_value DECIMAL(15, 2),
        cost_basis DECIMAL(15, 2),
        unrealized_pl DECIMAL(15, 2),
        realized_pl DECIMAL(15, 2),
        side VARCHAR(10),
        last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
      );
    `);
  });

  beforeEach(async () => {
    await testDatabase.query('DELETE FROM positions');
    await testDatabase.query('DELETE FROM user_portfolios'); 
    await testDatabase.query('DELETE FROM api_keys');
    
    // Insert test API key
    await testDatabase.query(`
      INSERT INTO api_keys (user_id, provider, encrypted_data, salt, iv)
      VALUES ('test-user-123', 'alpaca', 'encrypted-key-data', 'test-salt', 'test-iv')
    `);
  });

  describe('Account Information', () => {
    test('should fetch account details successfully', async () => {
      // Mock Alpaca API response
      const mockAccountData = {
        id: 'test-account-id',
        account_number: '123456789',
        status: 'ACTIVE',
        currency: 'USD',
        buying_power: '10000.00',
        regt_buying_power: '10000.00',
        daytrading_buying_power: '40000.00',
        cash: '5000.00',
        portfolio_value: '15000.00',
        equity: '15000.00',
        last_equity: '14500.00',
        multiplier: '4',
        daytrade_count: 0,
        pattern_day_trader: false,
        trading_blocked: false,
        transfers_blocked: false,
        account_blocked: false,
        created_at: '2023-01-15T10:30:00Z'
      };

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockAccountData);

      const result = await alpacaService.getAccountInfo('test-user-123');

      expect(result.success).toBe(true);
      expect(result.data.account_number).toBe('123456789');
      expect(result.data.status).toBe('ACTIVE');
      expect(parseFloat(result.data.buying_power)).toBe(10000.00);
      expect(result.data.pattern_day_trader).toBe(false);
    });

    test('should handle account fetch errors', async () => {
      jest.spyOn(alpacaService, 'makeRequest').mockRejectedValue({
        status: 403,
        message: 'Forbidden'
      });

      const result = await alpacaService.getAccountInfo('test-user-123');

      expect(result.success).toBe(false);
      expect(result.error.status).toBe(403);
      expect(result.error.message).toContain('Forbidden');
    });

    test('should sync account data to database', async () => {
      const mockAccountData = {
        id: 'alpaca-account-123',
        status: 'ACTIVE',
        buying_power: '25000.00',
        portfolio_value: '30000.00',
        daytrade_count: 2
      };

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockAccountData);

      await alpacaService.syncAccountData('test-user-123');

      const portfolioResult = await testDatabase.query(
        'SELECT * FROM user_portfolios WHERE user_id = $1',
        ['test-user-123']
      );

      expect(portfolioResult.rows).toHaveLength(1);
      const portfolio = portfolioResult.rows[0];
      expect(portfolio.alpaca_account_id).toBe('alpaca-account-123');
      expect(parseFloat(portfolio.buying_power)).toBe(25000.00);
      expect(parseFloat(portfolio.portfolio_value)).toBe(30000.00);
      expect(portfolio.day_trade_count).toBe(2);
    });
  });

  describe('Position Management', () => {
    test('should fetch positions successfully', async () => {
      const mockPositions = [
        {
          asset_id: 'asset-1',
          symbol: 'AAPL',
          exchange: 'NASDAQ',
          asset_class: 'us_equity',
          qty: '10',
          side: 'long',
          market_value: '1890.00',
          cost_basis: '1850.00',
          unrealized_pl: '40.00',
          unrealized_plpc: '0.0216',
          unrealized_intraday_pl: '15.00',
          unrealized_intraday_plpc: '0.0081',
          current_price: '189.00',
          lastday_price: '187.50',
          change_today: '1.50'
        },
        {
          asset_id: 'asset-2',
          symbol: 'MSFT',
          exchange: 'NASDAQ',
          asset_class: 'us_equity',
          qty: '5',
          side: 'long',
          market_value: '1750.00',
          cost_basis: '1725.00',
          unrealized_pl: '25.00',
          unrealized_plpc: '0.0145',
          current_price: '350.00',
          lastday_price: '348.00',
          change_today: '2.00'
        }
      ];

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockPositions);

      const result = await alpacaService.getPositions('test-user-123');

      expect(result.success).toBe(true);
      expect(result.data).toHaveLength(2);
      
      const applePosition = result.data.find(p => p.symbol === 'AAPL');
      expect(applePosition.qty).toBe('10');
      expect(parseFloat(applePosition.market_value)).toBe(1890.00);
      expect(parseFloat(applePosition.unrealized_pl)).toBe(40.00);
    });

    test('should sync positions to database', async () => {
      const mockPositions = [
        {
          symbol: 'AAPL',
          qty: '15',
          side: 'long',
          market_value: '2835.00',
          cost_basis: '2800.00',
          unrealized_pl: '35.00'
        }
      ];

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockPositions);

      await alpacaService.syncPositions('test-user-123');

      const positionsResult = await testDatabase.query(
        'SELECT * FROM positions WHERE user_id = $1',
        ['test-user-123']
      );

      expect(positionsResult.rows).toHaveLength(1);
      const position = positionsResult.rows[0];
      expect(position.symbol).toBe('AAPL');
      expect(parseFloat(position.quantity)).toBe(15);
      expect(parseFloat(position.market_value)).toBe(2835.00);
      expect(parseFloat(position.unrealized_pl)).toBe(35.00);
    });

    test('should handle empty positions', async () => {
      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue([]);

      const result = await alpacaService.getPositions('test-user-123');

      expect(result.success).toBe(true);
      expect(result.data).toEqual([]);
    });
  });

  describe('Order Management', () => {
    test('should place market order successfully', async () => {
      const mockOrderResponse = {
        id: 'order-123',
        client_order_id: 'client-order-456',
        created_at: '2024-01-15T10:30:00Z',
        updated_at: '2024-01-15T10:30:00Z',
        submitted_at: '2024-01-15T10:30:00Z',
        filled_at: null,
        expired_at: null,
        canceled_at: null,
        failed_at: null,
        replaced_at: null,
        replaced_by: null,
        replaces: null,
        asset_id: 'asset-123',
        symbol: 'AAPL',
        asset_class: 'us_equity',
        notional: null,
        qty: '10',
        filled_qty: '0',
        filled_avg_price: null,
        order_class: '',
        order_type: 'market',
        type: 'market',
        side: 'buy',
        time_in_force: 'day',
        limit_price: null,
        stop_price: null,
        status: 'accepted',
        extended_hours: false,
        legs: null,
        trail_percent: null,
        trail_price: null,
        hwm: null
      };

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockOrderResponse);

      const orderData = {
        symbol: 'AAPL',
        qty: '10',
        side: 'buy',
        type: 'market',
        time_in_force: 'day'
      };

      const result = await alpacaService.placeOrder('test-user-123', orderData);

      expect(result.success).toBe(true);
      expect(result.data.id).toBe('order-123');
      expect(result.data.symbol).toBe('AAPL');
      expect(result.data.status).toBe('accepted');
      expect(result.data.side).toBe('buy');
    });

    test('should place limit order successfully', async () => {
      const mockOrderResponse = {
        id: 'limit-order-123',
        symbol: 'MSFT',
        qty: '5',
        side: 'sell',
        order_type: 'limit',
        limit_price: '355.00',
        status: 'accepted'
      };

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockOrderResponse);

      const orderData = {
        symbol: 'MSFT',
        qty: '5',
        side: 'sell',
        type: 'limit',
        limit_price: '355.00',
        time_in_force: 'gtc'
      };

      const result = await alpacaService.placeOrder('test-user-123', orderData);

      expect(result.success).toBe(true);
      expect(result.data.order_type).toBe('limit');
      expect(result.data.limit_price).toBe('355.00');
    });

    test('should handle order validation errors', async () => {
      const validationErrors = [
        { symbol: '', qty: '10', side: 'buy', type: 'market' }, // Missing symbol
        { symbol: 'AAPL', qty: '0', side: 'buy', type: 'market' }, // Invalid quantity
        { symbol: 'AAPL', qty: '10', side: 'invalid', type: 'market' }, // Invalid side
        { symbol: 'AAPL', qty: '10', side: 'buy', type: 'limit' } // Missing limit price for limit order
      ];

      for (const invalidOrder of validationErrors) {
        const result = await alpacaService.placeOrder('test-user-123', invalidOrder);
        expect(result.success).toBe(false);
        expect(result.error.type).toBe('validation_error');
      }
    });

    test('should handle order rejection', async () => {
      jest.spyOn(alpacaService, 'makeRequest').mockRejectedValue({
        code: 40010001,
        message: 'insufficient buying power'
      });

      const orderData = {
        symbol: 'AAPL',
        qty: '1000',
        side: 'buy',
        type: 'market'
      };

      const result = await alpacaService.placeOrder('test-user-123', orderData);

      expect(result.success).toBe(false);
      expect(result.error.code).toBe(40010001);
      expect(result.error.message).toContain('insufficient buying power');
    });
  });

  describe('Historical Data', () => {
    test('should fetch price history successfully', async () => {
      const mockHistoricalData = {
        bars: [
          {
            t: '2024-01-15T09:30:00Z',
            o: 185.50,
            h: 189.75,
            l: 184.20,
            c: 189.45,
            v: 45672893
          },
          {
            t: '2024-01-16T09:30:00Z',
            o: 189.20,
            h: 192.10,
            l: 188.85,
            c: 191.75,
            v: 38945621
          }
        ],
        symbol: 'AAPL',
        next_page_token: null
      };

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockHistoricalData);

      const result = await alpacaService.getPriceHistory('test-user-123', 'AAPL', '2024-01-15', '2024-01-16');

      expect(result.success).toBe(true);
      expect(result.data.symbol).toBe('AAPL');
      expect(result.data.bars).toHaveLength(2);
      expect(result.data.bars[0].c).toBe(189.45);
      expect(result.data.bars[1].c).toBe(191.75);
    });

    test('should handle historical data pagination', async () => {
      const mockFirstPage = {
        bars: [{ t: '2024-01-15T09:30:00Z', c: 189.45 }],
        next_page_token: 'next-page-token'
      };

      const mockSecondPage = {
        bars: [{ t: '2024-01-16T09:30:00Z', c: 191.75 }],
        next_page_token: null
      };

      jest.spyOn(alpacaService, 'makeRequest')
        .mockResolvedValueOnce(mockFirstPage)
        .mockResolvedValueOnce(mockSecondPage);

      const result = await alpacaService.getPriceHistory('test-user-123', 'AAPL', '2024-01-15', '2024-01-16', { paginate: true });

      expect(result.success).toBe(true);
      expect(result.data.bars).toHaveLength(2);
    });
  });

  describe('API Rate Limiting', () => {
    test('should handle rate limiting with backoff', async () => {
      jest.spyOn(alpacaService, 'makeRequest')
        .mockRejectedValueOnce({ status: 429, message: 'Rate limit exceeded' })
        .mockResolvedValueOnce({ id: 'success-after-retry' });

      const result = await alpacaService.getAccountInfo('test-user-123');

      expect(result.success).toBe(true);
      expect(result.data.id).toBe('success-after-retry');
    });

    test('should respect rate limits across requests', async () => {
      const startTime = Date.now();
      
      const requests = Array.from({ length: 5 }, () =>
        alpacaService.getAccountInfo('test-user-123')
      );

      await Promise.all(requests);
      
      const duration = Date.now() - startTime;
      // Should take some time due to rate limiting
      expect(duration).toBeGreaterThan(100);
    });
  });

  describe('Error Handling and Resilience', () => {
    test('should handle network timeouts', async () => {
      jest.spyOn(alpacaService, 'makeRequest').mockRejectedValue({
        code: 'TIMEOUT',
        message: 'Request timeout'
      });

      const result = await alpacaService.getAccountInfo('test-user-123');

      expect(result.success).toBe(false);
      expect(result.error.code).toBe('TIMEOUT');
      expect(result.retryable).toBe(true);
    });

    test('should handle API key validation errors', async () => {
      jest.spyOn(alpacaService, 'makeRequest').mockRejectedValue({
        status: 401,
        message: 'Invalid API key'
      });

      const result = await alpacaService.getAccountInfo('test-user-123');

      expect(result.success).toBe(false);
      expect(result.error.status).toBe(401);
      expect(result.requiresReauth).toBe(true);
    });

    test('should handle market closed errors', async () => {
      jest.spyOn(alpacaService, 'makeRequest').mockRejectedValue({
        code: 40010000,
        message: 'market is closed'
      });

      const orderData = {
        symbol: 'AAPL',
        qty: '10',
        side: 'buy',
        type: 'market'
      };

      const result = await alpacaService.placeOrder('test-user-123', orderData);

      expect(result.success).toBe(false);
      expect(result.error.code).toBe(40010000);
      expect(result.error.temporary).toBe(true);
    });

    test('should sanitize sensitive data in error logs', async () => {
      const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
      
      jest.spyOn(alpacaService, 'makeRequest').mockRejectedValue({
        message: 'Error with API key: AKTEST123456789',
        config: {
          headers: {
            'APCA-API-KEY-ID': 'AKTEST123456789',
            'APCA-API-SECRET-KEY': 'secret123'
          }
        }
      });

      await alpacaService.getAccountInfo('test-user-123');

      // Check that sensitive data is not logged
      const logCalls = consoleSpy.mock.calls;
      logCalls.forEach(call => {
        const logMessage = JSON.stringify(call);
        expect(logMessage).not.toContain('AKTEST123456789');
        expect(logMessage).not.toContain('secret123');
      });

      consoleSpy.mockRestore();
    });
  });

  describe('Data Validation and Consistency', () => {
    test('should validate market data integrity', async () => {
      const mockInvalidData = {
        bars: [
          {
            t: '2024-01-15T09:30:00Z',
            o: -185.50, // Invalid negative price
            h: 189.75,
            l: 200.00,  // Low higher than high (invalid)
            c: 189.45,
            v: -1000    // Invalid negative volume
          }
        ]
      };

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockInvalidData);

      const result = await alpacaService.getPriceHistory('test-user-123', 'AAPL', '2024-01-15', '2024-01-15');

      expect(result.success).toBe(false);
      expect(result.error.type).toBe('data_validation_error');
      expect(result.error.message).toContain('invalid price data');
    });

    test('should validate position data consistency', async () => {
      const mockInconsistentPositions = [
        {
          symbol: 'AAPL',
          qty: '10',
          market_value: '1890.00',
          current_price: '200.00' // Would make market value 2000, not 1890
        }
      ];

      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockInconsistentPositions);

      const result = await alpacaService.getPositions('test-user-123');

      expect(result.success).toBe(false);
      expect(result.error.type).toBe('data_consistency_error');
    });
  });

  describe('Performance and Caching', () => {
    test('should cache account data appropriately', async () => {
      const mockAccountData = { id: 'test-account', status: 'ACTIVE' };
      const requestSpy = jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockAccountData);

      // First call
      await alpacaService.getAccountInfo('test-user-123');
      // Second call within cache period
      await alpacaService.getAccountInfo('test-user-123');

      // Should only make one actual API call
      expect(requestSpy).toHaveBeenCalledTimes(1);
    });

    test('should handle concurrent identical requests efficiently', async () => {
      const mockData = { id: 'test-account' };
      jest.spyOn(alpacaService, 'makeRequest').mockResolvedValue(mockData);

      const concurrentRequests = Array.from({ length: 3 }, () =>
        alpacaService.getAccountInfo('test-user-123')
      );

      const results = await Promise.all(concurrentRequests);

      // All should succeed with same data
      results.forEach(result => {
        expect(result.success).toBe(true);
        expect(result.data.id).toBe('test-account');
      });
    });
  });
});