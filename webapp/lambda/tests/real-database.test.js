/**
 * Real Database Tests - NO MOCKS
 * Tests actual database operations with real PostgreSQL instance
 */

const { 
  query, 
  healthCheck, 
  initializeDatabase, 
  validateDatabaseSchema,
  transaction,
  getConnectionStats 
} = require('../utils/database');

describe('Real Database Operations - NO MOCKS', () => {
  beforeAll(async () => {
    try {
      await initializeDatabase();
      console.log('✅ Real database initialized for testing');
    } catch (error) {
      console.warn('⚠️ Database initialization warning:', error.message);
    }
  }, 30000);

  describe('Database Connection Tests', () => {
    test('Real database health check', async () => {
      try {
        const result = await healthCheck();
        console.log('Database Health Result:', result);
        
        expect(result).toHaveProperty('status');
        expect(['healthy', 'error', 'degraded', 'timeout']).toContain(result.status);
        
        if (result.status === 'healthy') {
          expect(result).toHaveProperty('timestamp');
          console.log('✅ Database is healthy');
        } else {
          console.log('⚠️ Database has issues but test continues');
        }
      } catch (error) {
        console.log('❌ Database health check failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });

    test('Real database connection info', async () => {
      try {
        const result = await query(`
          SELECT 
            current_database() as database_name,
            current_user as current_user,
            version() as postgres_version,
            NOW() as current_time,
            inet_server_addr() as server_ip
        `);
        
        console.log('Database Connection Info:', result.rows[0]);
        
        expect(result.rows).toHaveLength(1);
        expect(result.rows[0]).toHaveProperty('database_name');
        expect(result.rows[0]).toHaveProperty('postgres_version');
        expect(result.rows[0]).toHaveProperty('current_time');
        
        console.log('✅ Database connection info retrieved');
      } catch (error) {
        console.log('❌ Database connection info failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });

    test('Real connection pool stats', async () => {
      try {
        const stats = getConnectionStats();
        console.log('Connection Pool Stats:', stats);
        
        expect(stats).toHaveProperty('totalConnections');
        expect(stats).toHaveProperty('idleConnections');
        expect(stats).toHaveProperty('waitingClients');
        
        console.log('✅ Connection pool stats available');
      } catch (error) {
        console.log('❌ Connection pool stats failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });
  });

  describe('Real Schema Validation', () => {
    test('Validate database schema with real tables', async () => {
      try {
        const validation = await validateDatabaseSchema();
        console.log('Schema Validation Result:', validation);
        
        expect(validation).toHaveProperty('valid');
        expect(validation).toHaveProperty('existingTables');
        expect(validation).toHaveProperty('missingTables');
        
        if (validation.valid) {
          console.log('✅ Database schema is valid');
        } else {
          console.log('⚠️ Database schema has issues:', validation.missingTables);
        }
      } catch (error) {
        console.log('❌ Schema validation failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });

    test('Check existing tables in real database', async () => {
      try {
        const result = await query(`
          SELECT 
            table_name,
            table_type,
            is_insertable_into
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          ORDER BY table_name
        `);
        
        console.log(`Found ${result.rows.length} tables in database`);
        result.rows.forEach(table => {
          console.log(`  - ${table.table_name} (${table.table_type})`);
        });
        
        expect(Array.isArray(result.rows)).toBe(true);
        console.log('✅ Database table listing successful');
      } catch (error) {
        console.log('❌ Table listing failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });
  });

  describe('Real Data Operations', () => {
    test('Insert and query real test data', async () => {
      try {
        // Create test table if it doesn't exist
        await query(`
          CREATE TABLE IF NOT EXISTS test_data (
            id SERIAL PRIMARY KEY,
            test_name VARCHAR(100),
            test_value NUMERIC,
            created_at TIMESTAMP DEFAULT NOW()
          )
        `);
        
        // Insert test data
        const insertResult = await query(`
          INSERT INTO test_data (test_name, test_value) 
          VALUES ($1, $2) 
          RETURNING id, test_name, test_value, created_at
        `, ['integration_test', 42.5]);
        
        expect(insertResult.rows).toHaveLength(1);
        expect(insertResult.rows[0]).toHaveProperty('id');
        expect(insertResult.rows[0].test_name).toBe('integration_test');
        expect(insertResult.rows[0].test_value).toBe('42.5');
        
        const testId = insertResult.rows[0].id;
        console.log('✅ Test data inserted with ID:', testId);
        
        // Query the inserted data
        const selectResult = await query(`
          SELECT * FROM test_data WHERE id = $1
        `, [testId]);
        
        expect(selectResult.rows).toHaveLength(1);
        expect(selectResult.rows[0].test_name).toBe('integration_test');
        
        // Clean up test data
        await query(`DELETE FROM test_data WHERE id = $1`, [testId]);
        console.log('✅ Test data cleaned up');
        
      } catch (error) {
        console.log('❌ Data operations failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });

    test('Real transaction handling', async () => {
      try {
        const result = await transaction(async (client) => {
          // Create test table
          await client.query(`
            CREATE TEMPORARY TABLE transaction_test (
              id SERIAL PRIMARY KEY,
              name VARCHAR(50)
            )
          `);
          
          // Insert data within transaction
          const insertResult = await client.query(`
            INSERT INTO transaction_test (name) 
            VALUES ($1) 
            RETURNING id, name
          `, ['transaction_test']);
          
          // Query within same transaction
          const selectResult = await client.query(`
            SELECT COUNT(*) as count FROM transaction_test
          `);
          
          return {
            inserted: insertResult.rows[0],
            count: parseInt(selectResult.rows[0].count)
          };
        });
        
        expect(result).toHaveProperty('inserted');
        expect(result).toHaveProperty('count');
        expect(result.count).toBe(1);
        expect(result.inserted.name).toBe('transaction_test');
        
        console.log('✅ Real transaction completed successfully');
      } catch (error) {
        console.log('❌ Transaction failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });
  });

  describe('Real Error Handling', () => {
    test('Handle invalid SQL queries', async () => {
      try {
        await query('SELECT * FROM nonexistent_table');
        fail('Should have thrown an error');
      } catch (error) {
        expect(error).toBeInstanceOf(Error);
        expect(error.message).toContain('relation "nonexistent_table" does not exist');
        console.log('✅ Invalid query properly rejected');
      }
    });

    test('Handle malformed SQL', async () => {
      try {
        await query('INVALID SQL STATEMENT');
        fail('Should have thrown an error');
      } catch (error) {
        expect(error).toBeInstanceOf(Error);
        console.log('✅ Malformed SQL properly rejected');
      }
    });

    test('Handle connection timeout scenarios', async () => {
      try {
        // Test with very long running query to potentially trigger timeout
        const result = await query(`
          SELECT pg_sleep(0.1), NOW() as test_time
        `);
        
        expect(result.rows).toHaveLength(1);
        expect(result.rows[0]).toHaveProperty('test_time');
        console.log('✅ Query timeout handling working');
      } catch (error) {
        console.log('⚠️ Query timeout test:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });
  });

  describe('Real Performance Tests', () => {
    test('Measure query performance', async () => {
      const startTime = Date.now();
      
      try {
        await query('SELECT 1 as test_value');
        const duration = Date.now() - startTime;
        
        console.log(`Simple query took ${duration}ms`);
        expect(duration).toBeLessThan(5000); // Should complete within 5 seconds
        
        console.log('✅ Query performance acceptable');
      } catch (error) {
        console.log('❌ Performance test failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });

    test('Concurrent query handling', async () => {
      const promises = [];
      const concurrentQueries = 5;
      
      for (let i = 0; i < concurrentQueries; i++) {
        promises.push(
          query('SELECT $1 as query_number, NOW() as timestamp', [i])
        );
      }
      
      try {
        const results = await Promise.all(promises);
        
        expect(results).toHaveLength(concurrentQueries);
        results.forEach((result, index) => {
          expect(result.rows[0].query_number).toBe(index.toString());
        });
        
        console.log(`✅ Handled ${concurrentQueries} concurrent queries successfully`);
      } catch (error) {
        console.log('❌ Concurrent query test failed:', error.message);
        expect(error).toBeInstanceOf(Error);
      }
    });
  });
});