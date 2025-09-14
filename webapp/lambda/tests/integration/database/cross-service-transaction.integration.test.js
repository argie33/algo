/**
 * Cross-Service Transaction Integration Tests
 * Tests transaction coordination across multiple service boundaries
 * Validates distributed transaction patterns and data consistency
 */

const { initializeDatabase, closeDatabase, transaction } = require("../../../utils/database");

describe("Cross-Service Transaction Integration", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Service Coordination Patterns", () => {
    test("should coordinate portfolio and order service transactions", async () => {
      // Create tables representing different service domains
      await transaction(async (client) => {
        // Portfolio service tables
        await client.query(`
          CREATE TEMPORARY TABLE portfolio_positions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            symbol TEXT,
            quantity DECIMAL(15,4),
            avg_price DECIMAL(10,2),
            updated_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Order service tables
        await client.query(`
          CREATE TEMPORARY TABLE orders (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            symbol TEXT,
            action TEXT,
            quantity DECIMAL(15,4),
            price DECIMAL(10,2),
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Audit trail service table
        await client.query(`
          CREATE TEMPORARY TABLE transaction_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            service TEXT,
            action TEXT,
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Initial portfolio position
        await client.query(`
          INSERT INTO portfolio_positions (user_id, symbol, quantity, avg_price) 
          VALUES (1, 'AAPL', 100, 150.00)
        `);
      });

      // Cross-service transaction: Sell order execution
      const sellOrderExecution = await transaction(async (client) => {
        const userId = 1;
        const symbol = 'AAPL';
        const sellQuantity = 30;
        const sellPrice = 160.00;
        
        // Step 1: Order service - Create sell order
        const orderResult = await client.query(`
          INSERT INTO orders (user_id, symbol, action, quantity, price, status) 
          VALUES ($1, $2, 'SELL', $3, $4, 'executing') 
          RETURNING id
        `, [userId, symbol, sellQuantity, sellPrice]);
        
        const orderId = orderResult.rows[0].id;
        
        // Step 2: Portfolio service - Check position availability
        const positionResult = await client.query(`
          SELECT quantity FROM portfolio_positions 
          WHERE user_id = $1 AND symbol = $2 FOR UPDATE
        `, [userId, symbol]);
        
        if (positionResult.rows.length === 0) {
          throw new Error('Position not found');
        }
        
        const currentQuantity = parseFloat(positionResult.rows[0].quantity);
        if (currentQuantity < sellQuantity) {
          throw new Error('Insufficient shares for sale');
        }
        
        // Step 3: Portfolio service - Update position
        await client.query(`
          UPDATE portfolio_positions 
          SET quantity = quantity - $1, updated_at = NOW() 
          WHERE user_id = $2 AND symbol = $3
        `, [sellQuantity, userId, symbol]);
        
        // Step 4: Order service - Complete order
        await client.query(`
          UPDATE orders SET status = 'completed' WHERE id = $1
        `, [orderId]);
        
        // Step 5: Audit service - Log transaction
        await client.query(`
          INSERT INTO transaction_log (user_id, service, action, details) 
          VALUES ($1, 'cross-service', 'sell_execution', $2)
        `, [userId, JSON.stringify({
          orderId,
          symbol,
          quantity: sellQuantity,
          price: sellPrice,
          originalPosition: currentQuantity
        })]);
        
        return {
          orderId,
          remainingShares: currentQuantity - sellQuantity,
          transactionValue: sellQuantity * sellPrice
        };
      });

      expect(sellOrderExecution.orderId).toBeDefined();
      expect(sellOrderExecution.remainingShares).toBe(70);
      expect(sellOrderExecution.transactionValue).toBe(4800); // 30 * 160

      // Verify final state across all services
      await transaction(async (client) => {
        // Check portfolio state
        const positionResult = await client.query(
          "SELECT quantity FROM portfolio_positions WHERE user_id = 1 AND symbol = 'AAPL'"
        );
        expect(parseFloat(positionResult.rows[0].quantity)).toBe(70);
        
        // Check order state
        const orderResult = await client.query(
          "SELECT status FROM orders WHERE id = $1",
          [sellOrderExecution.orderId]
        );
        expect(orderResult.rows[0].status).toBe('completed');
        
        // Check audit log
        const auditResult = await client.query(
          "SELECT details FROM transaction_log WHERE service = 'cross-service'"
        );
        expect(auditResult.rows).toHaveLength(1);
        
        const logDetails = auditResult.rows[0].details;
        expect(logDetails.symbol).toBe('AAPL');
        expect(logDetails.quantity).toBe(30);
      });
    });

    test("should handle cross-service transaction failure and rollback", async () => {
      // Setup test data
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE account_balance (
            user_id INTEGER PRIMARY KEY,
            balance DECIMAL(15,2),
            currency TEXT DEFAULT 'USD'
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE trade_executions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            symbol TEXT,
            action TEXT,
            quantity DECIMAL(15,4),
            price DECIMAL(10,2),
            total_cost DECIMAL(15,2),
            status TEXT DEFAULT 'pending'
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE market_data (
            symbol TEXT PRIMARY KEY,
            current_price DECIMAL(10,2),
            available_shares INTEGER,
            last_updated TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Initial state
        await client.query("INSERT INTO account_balance (user_id, balance) VALUES (1, 10000.00)");
        await client.query("INSERT INTO market_data (symbol, current_price, available_shares) VALUES ('GOOGL', 2500.00, 100)");
      });

      // Cross-service transaction that should fail
      const failedBuyTransaction = transaction(async (client) => {
        const userId = 1;
        const symbol = 'GOOGL';
        const buyQuantity = 5;
        const maxPrice = 2600.00;
        
        // Step 1: Market data service - Check current price and availability
        const marketResult = await client.query(
          "SELECT current_price, available_shares FROM market_data WHERE symbol = $1 FOR UPDATE",
          [symbol]
        );
        
        const currentPrice = parseFloat(marketResult.rows[0].current_price);
        const availableShares = marketResult.rows[0].available_shares;
        
        if (availableShares < buyQuantity) {
          throw new Error('Insufficient shares available in market');
        }
        
        // Step 2: Account service - Check balance
        const balanceResult = await client.query(
          "SELECT balance FROM account_balance WHERE user_id = $1 FOR UPDATE",
          [userId]
        );
        
        const currentBalance = parseFloat(balanceResult.rows[0].balance);
        const totalCost = buyQuantity * currentPrice;
        
        if (currentBalance < totalCost) {
          throw new Error('Insufficient account balance');
        }
        
        // Step 3: Trade execution service - Create trade record
        const tradeResult = await client.query(`
          INSERT INTO trade_executions (user_id, symbol, action, quantity, price, total_cost, status) 
          VALUES ($1, $2, 'BUY', $3, $4, $5, 'processing') 
          RETURNING id
        `, [userId, symbol, buyQuantity, currentPrice, totalCost]);
        
        const tradeId = tradeResult.rows[0].id;
        
        // Step 4: Market validation (simulate market rejection)
        if (currentPrice > maxPrice) {
          throw new Error(`Market price ${currentPrice} exceeds maximum ${maxPrice}`);
        }
        
        // This won't execute due to price check failure
        await client.query("UPDATE account_balance SET balance = balance - $1 WHERE user_id = $2", [totalCost, userId]);
        await client.query("UPDATE market_data SET available_shares = available_shares - $1 WHERE symbol = $2", [buyQuantity, symbol]);
        await client.query("UPDATE trade_executions SET status = 'completed' WHERE id = $1", [tradeId]);
        
        return { tradeId, totalCost };
      });

      await expect(failedBuyTransaction).rejects.toThrow('exceeds maximum');

      // Verify complete rollback across all services
      await transaction(async (client) => {
        // Account balance should be unchanged
        const balanceResult = await client.query("SELECT balance FROM account_balance WHERE user_id = 1");
        expect(parseFloat(balanceResult.rows[0].balance)).toBe(10000.00);
        
        // Market data should be unchanged
        const marketResult = await client.query("SELECT available_shares FROM market_data WHERE symbol = 'GOOGL'");
        expect(marketResult.rows[0].available_shares).toBe(100);
        
        // No trade executions should exist
        const tradeResult = await client.query("SELECT COUNT(*) as count FROM trade_executions");
        expect(parseInt(tradeResult.rows[0].count)).toBe(0);
      });
    });
  });

  describe("Service Dependency Management", () => {
    test("should handle service dependency chain transactions", async () => {
      // Create tables representing service dependency chain
      await transaction(async (client) => {
        // User service
        await client.query(`
          CREATE TEMPORARY TABLE user_profiles (
            user_id INTEGER PRIMARY KEY,
            risk_level TEXT,
            trading_enabled BOOLEAN DEFAULT true
          )
        `);
        
        // Risk management service
        await client.query(`
          CREATE TEMPORARY TABLE risk_limits (
            user_id INTEGER PRIMARY KEY,
            max_position_value DECIMAL(15,2),
            max_daily_trades INTEGER,
            current_daily_trades INTEGER DEFAULT 0
          )
        `);
        
        // Compliance service
        await client.query(`
          CREATE TEMPORARY TABLE compliance_checks (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            check_type TEXT,
            status TEXT,
            details JSONB,
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Trading service
        await client.query(`
          CREATE TEMPORARY TABLE active_trades (
            id SERIAL PRIMARY KEY,
            user_id INTEGER,
            symbol TEXT,
            quantity DECIMAL(15,4),
            value DECIMAL(15,2),
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Setup initial data
        await client.query("INSERT INTO user_profiles (user_id, risk_level) VALUES (1, 'moderate')");
        await client.query("INSERT INTO risk_limits (user_id, max_position_value, max_daily_trades) VALUES (1, 50000.00, 10)");
      });

      // Service dependency chain transaction
      const dependencyChainTransaction = await transaction(async (client) => {
        const userId = 1;
        const symbol = 'TSLA';
        const tradeValue = 15000.00;
        const quantity = 10;
        
        // Step 1: User service - Verify user can trade
        const userResult = await client.query(
          "SELECT risk_level, trading_enabled FROM user_profiles WHERE user_id = $1",
          [userId]
        );
        
        if (!userResult.rows[0].trading_enabled) {
          throw new Error('Trading not enabled for user');
        }
        
        const riskLevel = userResult.rows[0].risk_level;
        
        // Step 2: Risk management service - Check limits
        const riskResult = await client.query(
          "SELECT max_position_value, max_daily_trades, current_daily_trades FROM risk_limits WHERE user_id = $1 FOR UPDATE",
          [userId]
        );
        
        const { max_position_value, max_daily_trades, current_daily_trades } = riskResult.rows[0];
        
        if (tradeValue > parseFloat(max_position_value)) {
          throw new Error('Trade value exceeds position limit');
        }
        
        if (current_daily_trades >= max_daily_trades) {
          throw new Error('Daily trade limit exceeded');
        }
        
        // Step 3: Compliance service - Perform compliance check
        const complianceResult = await client.query(`
          INSERT INTO compliance_checks (user_id, check_type, status, details) 
          VALUES ($1, 'trade_approval', 'checking', $2) 
          RETURNING id
        `, [userId, JSON.stringify({ symbol, value: tradeValue, riskLevel })]);
        
        const complianceId = complianceResult.rows[0].id;
        
        // Simulate compliance validation
        const riskScore = tradeValue / parseFloat(max_position_value);
        if (riskScore > 0.8 && riskLevel === 'conservative') {
          await client.query(
            "UPDATE compliance_checks SET status = 'rejected' WHERE id = $1",
            [complianceId]
          );
          throw new Error('Compliance rejection: High risk for conservative profile');
        }
        
        await client.query(
          "UPDATE compliance_checks SET status = 'approved' WHERE id = $1",
          [complianceId]
        );
        
        // Step 4: Trading service - Execute trade
        const tradeResult = await client.query(`
          INSERT INTO active_trades (user_id, symbol, quantity, value, status) 
          VALUES ($1, $2, $3, $4, 'executed') 
          RETURNING id
        `, [userId, symbol, quantity, tradeValue]);
        
        const tradeId = tradeResult.rows[0].id;
        
        // Step 5: Risk management service - Update counters
        await client.query(
          "UPDATE risk_limits SET current_daily_trades = current_daily_trades + 1 WHERE user_id = $1",
          [userId]
        );
        
        return {
          tradeId,
          complianceId,
          riskScore,
          approvedValue: tradeValue
        };
      });

      expect(dependencyChainTransaction.tradeId).toBeDefined();
      expect(dependencyChainTransaction.complianceId).toBeDefined();
      expect(dependencyChainTransaction.riskScore).toBeLessThan(0.8);

      // Verify state across all dependent services
      await transaction(async (client) => {
        // Risk limits updated
        const riskResult = await client.query("SELECT current_daily_trades FROM risk_limits WHERE user_id = 1");
        expect(riskResult.rows[0].current_daily_trades).toBe(1);
        
        // Compliance check recorded
        const complianceResult = await client.query("SELECT status FROM compliance_checks WHERE id = $1", [dependencyChainTransaction.complianceId]);
        expect(complianceResult.rows[0].status).toBe('approved');
        
        // Trade executed
        const tradeResult = await client.query("SELECT status, value FROM active_trades WHERE id = $1", [dependencyChainTransaction.tradeId]);
        expect(tradeResult.rows[0].status).toBe('executed');
        expect(parseFloat(tradeResult.rows[0].value)).toBe(15000.00);
      });
    });

    test("should handle circular dependency resolution", async () => {
      // Create tables with circular dependencies
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE service_a (
            id SERIAL PRIMARY KEY,
            value INTEGER,
            dependent_on_b INTEGER,
            status TEXT DEFAULT 'pending'
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE service_b (
            id SERIAL PRIMARY KEY,
            value INTEGER,
            dependent_on_a INTEGER,
            status TEXT DEFAULT 'pending'
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE coordination_log (
            id SERIAL PRIMARY KEY,
            operation TEXT,
            step INTEGER,
            service TEXT,
            details TEXT,
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
      });

      // Handle circular dependency through coordination
      const circularDependencyResolution = await transaction(async (client) => {
        const operationId = 'circular_op_1';
        
        // Step 1: Initialize both services with temporary state
        await client.query(`
          INSERT INTO coordination_log (operation, step, service, details) 
          VALUES ($1, 1, 'coordinator', 'Starting circular dependency resolution')
        `, [operationId]);
        
        const serviceAResult = await client.query(`
          INSERT INTO service_a (value, status) 
          VALUES (100, 'initializing') 
          RETURNING id
        `);
        const serviceAId = serviceAResult.rows[0].id;
        
        const serviceBResult = await client.query(`
          INSERT INTO service_b (value, status) 
          VALUES (200, 'initializing') 
          RETURNING id
        `);
        const serviceBId = serviceBResult.rows[0].id;
        
        await client.query(`
          INSERT INTO coordination_log (operation, step, service, details) 
          VALUES ($1, 2, 'both', 'Services initialized with IDs: A=' || $2 || ', B=' || $3)
        `, [operationId, serviceAId, serviceBId]);
        
        // Step 2: Establish cross-references
        await client.query(
          "UPDATE service_a SET dependent_on_b = $1 WHERE id = $2",
          [serviceBId, serviceAId]
        );
        
        await client.query(
          "UPDATE service_b SET dependent_on_a = $1 WHERE id = $2",
          [serviceAId, serviceBId]
        );
        
        await client.query(`
          INSERT INTO coordination_log (operation, step, service, details) 
          VALUES ($1, 3, 'coordinator', 'Cross-references established')
        `, [operationId]);
        
        // Step 3: Coordinated completion
        await client.query("UPDATE service_a SET status = 'completed' WHERE id = $1", [serviceAId]);
        await client.query("UPDATE service_b SET status = 'completed' WHERE id = $1", [serviceBId]);
        
        await client.query(`
          INSERT INTO coordination_log (operation, step, service, details) 
          VALUES ($1, 4, 'coordinator', 'Circular dependency resolved successfully')
        `, [operationId]);
        
        return {
          serviceAId,
          serviceBId,
          operationId
        };
      });

      // Verify circular dependency was resolved
      await transaction(async (client) => {
        // Check service A state
        const serviceAResult = await client.query("SELECT * FROM service_a WHERE id = $1", [circularDependencyResolution.serviceAId]);
        const serviceA = serviceAResult.rows[0];
        expect(serviceA.status).toBe('completed');
        expect(serviceA.dependent_on_b).toBe(circularDependencyResolution.serviceBId);
        
        // Check service B state
        const serviceBResult = await client.query("SELECT * FROM service_b WHERE id = $1", [circularDependencyResolution.serviceBId]);
        const serviceB = serviceBResult.rows[0];
        expect(serviceB.status).toBe('completed');
        expect(serviceB.dependent_on_a).toBe(circularDependencyResolution.serviceAId);
        
        // Verify coordination log
        const logResult = await client.query("SELECT COUNT(*) as steps FROM coordination_log WHERE operation = $1", [circularDependencyResolution.operationId]);
        expect(parseInt(logResult.rows[0].steps)).toBe(4);
      });
    });
  });

  describe("Distributed Transaction Patterns", () => {
    test("should implement saga pattern for long-running transactions", async () => {
      // Create tables for saga pattern implementation
      await transaction(async (client) => {
        await client.query(`
          CREATE TEMPORARY TABLE saga_state (
            saga_id TEXT PRIMARY KEY,
            current_step INTEGER DEFAULT 0,
            total_steps INTEGER,
            status TEXT DEFAULT 'running',
            rollback_needed BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE saga_steps (
            id SERIAL PRIMARY KEY,
            saga_id TEXT,
            step_number INTEGER,
            service TEXT,
            action TEXT,
            status TEXT DEFAULT 'pending',
            rollback_action TEXT,
            data JSONB,
            completed_at TIMESTAMP
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE order_processing (
            order_id TEXT PRIMARY KEY,
            status TEXT,
            total_amount DECIMAL(10,2)
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE inventory_reservations (
            id SERIAL PRIMARY KEY,
            order_id TEXT,
            product_id TEXT,
            quantity INTEGER,
            status TEXT DEFAULT 'reserved'
          )
        `);
        
        await client.query(`
          CREATE TEMPORARY TABLE payment_authorizations (
            id SERIAL PRIMARY KEY,
            order_id TEXT,
            amount DECIMAL(10,2),
            status TEXT DEFAULT 'pending'
          )
        `);
      });

      // Implement saga transaction
      const sagaExecution = await transaction(async (client) => {
        const sagaId = 'saga_order_001';
        const orderId = 'order_123';
        const totalAmount = 99.99;
        
        // Initialize saga
        await client.query(`
          INSERT INTO saga_state (saga_id, total_steps, status) 
          VALUES ($1, 3, 'running')
        `, [sagaId]);
        
        // Define saga steps
        const steps = [
          { step: 1, service: 'order', action: 'create_order', rollback: 'cancel_order' },
          { step: 2, service: 'inventory', action: 'reserve_items', rollback: 'release_items' },
          { step: 3, service: 'payment', action: 'authorize_payment', rollback: 'void_authorization' }
        ];
        
        for (const step of steps) {
          await client.query(`
            INSERT INTO saga_steps (saga_id, step_number, service, action, rollback_action, data) 
            VALUES ($1, $2, $3, $4, $5, $6)
          `, [sagaId, step.step, step.service, step.action, step.rollback, JSON.stringify({ orderId, totalAmount })]);
        }
        
        // Execute saga steps
        try {
          // Step 1: Create order
          await client.query(
            "INSERT INTO order_processing (order_id, status, total_amount) VALUES ($1, 'pending', $2)",
            [orderId, totalAmount]
          );
          await client.query(
            "UPDATE saga_steps SET status = 'completed', completed_at = NOW() WHERE saga_id = $1 AND step_number = 1",
            [sagaId]
          );
          
          // Step 2: Reserve inventory
          await client.query(
            "INSERT INTO inventory_reservations (order_id, product_id, quantity) VALUES ($1, 'prod_123', 2)",
            [orderId]
          );
          await client.query(
            "UPDATE saga_steps SET status = 'completed', completed_at = NOW() WHERE saga_id = $1 AND step_number = 2",
            [sagaId]
          );
          
          // Step 3: Authorize payment (simulate failure for rollback test)
          const paymentResult = await client.query(
            "INSERT INTO payment_authorizations (order_id, amount, status) VALUES ($1, $2, 'processing') RETURNING id",
            [orderId, totalAmount]
          );
          
          // Simulate payment authorization success
          await client.query(
            "UPDATE payment_authorizations SET status = 'authorized' WHERE id = $1",
            [paymentResult.rows[0].id]
          );
          await client.query(
            "UPDATE saga_steps SET status = 'completed', completed_at = NOW() WHERE saga_id = $1 AND step_number = 3",
            [sagaId]
          );
          
          // Complete saga
          await client.query(
            "UPDATE saga_state SET status = 'completed', current_step = 3 WHERE saga_id = $1",
            [sagaId]
          );
          
          return { sagaId, orderId, status: 'completed' };
          
        } catch (error) {
          // Mark saga for rollback
          await client.query(
            "UPDATE saga_state SET rollback_needed = true, status = 'rolling_back' WHERE saga_id = $1",
            [sagaId]
          );
          throw error;
        }
      });

      expect(sagaExecution.status).toBe('completed');

      // Verify saga completion
      await transaction(async (client) => {
        // Check saga state
        const sagaResult = await client.query("SELECT * FROM saga_state WHERE saga_id = $1", [sagaExecution.sagaId]);
        expect(sagaResult.rows[0].status).toBe('completed');
        expect(sagaResult.rows[0].rollback_needed).toBe(false);
        
        // Check all steps completed
        const stepsResult = await client.query(
          "SELECT COUNT(*) as completed_steps FROM saga_steps WHERE saga_id = $1 AND status = 'completed'",
          [sagaExecution.sagaId]
        );
        expect(parseInt(stepsResult.rows[0].completed_steps)).toBe(3);
        
        // Verify business state
        const orderResult = await client.query("SELECT status FROM order_processing WHERE order_id = $1", [sagaExecution.orderId]);
        expect(orderResult.rows[0].status).toBe('pending'); // Order created successfully
        
        const inventoryResult = await client.query("SELECT status FROM inventory_reservations WHERE order_id = $1", [sagaExecution.orderId]);
        expect(inventoryResult.rows[0].status).toBe('reserved');
        
        const paymentResult = await client.query("SELECT status FROM payment_authorizations WHERE order_id = $1", [sagaExecution.orderId]);
        expect(paymentResult.rows[0].status).toBe('authorized');
      });
    });
  });
});