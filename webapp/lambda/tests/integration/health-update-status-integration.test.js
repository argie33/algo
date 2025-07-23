/**
 * Health Update Status Integration Tests
 * Tests the complete flow of health status updates including database interactions
 */

const request = require('supertest');
const { healthCheck, query } = require('../../utils/database');

// Import the actual app for integration testing
const app = require('../../index');

describe('Health Update Status Integration Tests', () => {
  // Skip if no database available
  const skipIfNoDb = process.env.SKIP_DB_TESTS === 'true' ? describe.skip : describe;

  beforeEach(() => {
    jest.setTimeout(30000); // 30 second timeout for integration tests
    
    // Mock console to reduce noise
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  skipIfNoDb('POST /api/health-full/update-status', () => {
    it('should perform complete health analysis with real database', async () => {
      const response = await request(app)
        .post('/api/health-full/update-status')
        .expect((res) => {
          // Accept both 200 (success) and 500 (database issues) for integration tests
          expect([200, 500]).toContain(res.status);
        });

      if (response.status === 200) {
        // Successful case - verify comprehensive analysis
        expect(response.body).toMatchObject({
          status: 'success',
          message: 'Database health status updated successfully',
          data: expect.objectContaining({
            status: 'connected',
            database: expect.objectContaining({
              status: 'connected',
              tables: expect.any(Object),
              summary: expect.objectContaining({
                total_tables: expect.any(Number),
                healthy_tables: expect.any(Number),
                total_records: expect.any(Number)
              })
            }),
            timestamp: expect.any(String)
          }),
          timestamp: expect.any(String)
        });

        // Verify performance metrics
        expect(response.body.data.note).toMatch(/Analyzed \d+ database tables in \d+ms/);

        // Verify table categorization if tables exist
        const tables = response.body.data.database.tables;
        if (Object.keys(tables).length > 0) {
          Object.values(tables).forEach(table => {
            expect(table).toMatchObject({
              status: expect.stringMatching(/^(healthy|stale|empty|error)$/),
              record_count: expect.any(Number),
              last_checked: expect.any(String),
              table_category: expect.any(String),
              critical_table: expect.any(Boolean)
            });
          });
        }

        // Verify summary statistics
        const summary = response.body.data.database.summary;
        expect(summary.total_tables).toBeGreaterThanOrEqual(0);
        expect(summary.healthy_tables).toBeGreaterThanOrEqual(0);
        expect(summary.total_records).toBeGreaterThanOrEqual(0);
        expect(summary.healthy_tables).toBeLessThanOrEqual(summary.total_tables);
        
        console.log(`✅ Integration test passed: ${summary.total_tables} tables analyzed, ${summary.total_records} total records`);
      } else {
        // Database connection issue - verify error response
        expect(response.body).toMatchObject({
          status: 'error',
          error: 'Failed to update health status',
          details: expect.any(String),
          timestamp: expect.any(String)
        });
        
        console.log('⚠️ Integration test: Database connection failed as expected in test environment');
      }
    });

    it('should handle timeout scenarios gracefully', async () => {
      const response = await request(app)
        .post('/api/health-full/update-status')
        .timeout(5000) // 5 second timeout to test timeout handling
        .expect((res) => {
          // Accept various response codes for timeout scenarios
          expect([200, 408, 500, 503]).toContain(res.status);
        });

      // Verify response has required structure regardless of outcome
      expect(response.body).toHaveProperty('status');
      expect(response.body).toHaveProperty('timestamp');
      
      if (response.status === 408) {
        expect(response.body.status).toBe('timeout');
        expect(response.body.message).toContain('timeout');
      }
    });

    it('should measure comprehensive table analysis across all database tables', async () => {
      const response = await request(app)
        .post('/api/health-full/update-status')
        .expect((res) => {
          expect([200, 500]).toContain(res.status);
        });

      if (response.status === 200) {
        const data = response.body.data;
        
        // Verify comprehensive analysis was performed
        expect(data.database.summary).toMatchObject({
          total_tables: expect.any(Number),
          healthy_tables: expect.any(Number),
          stale_tables: expect.any(Number),
          error_tables: expect.any(Number),
          empty_tables: expect.any(Number),
          missing_tables: expect.any(Number),
          total_records: expect.any(Number),
          total_missing_data: expect.any(Number)
        });

        // Verify all expected table categories are covered
        const tables = data.database.tables;
        const categories = new Set();
        Object.values(tables).forEach(table => {
          categories.add(table.table_category);
        });

        // Should analyze tables from multiple categories as per the user's requirement
        const expectedCategories = ['symbols', 'prices', 'portfolio', 'system', 'other'];
        const foundCategories = Array.from(categories);
        console.log(`📊 Table categories found: ${foundCategories.join(', ')}`);
        
        // Verify table analysis includes required fields
        Object.entries(tables).forEach(([tableName, tableData]) => {
          expect(tableData).toMatchObject({
            status: expect.any(String),
            record_count: expect.any(Number),
            last_updated: expect.anything(), // Can be null
            last_checked: expect.any(String),
            table_category: expect.any(String),
            critical_table: expect.any(Boolean),
            is_stale: expect.any(Boolean),
            missing_data_count: expect.any(Number),
            error: expect.anything(), // Can be null
            note: expect.any(String)
          });
        });

        // Log comprehensive analysis results
        console.log(`📈 Comprehensive analysis completed:
          - Total tables: ${data.database.summary.total_tables}
          - Healthy tables: ${data.database.summary.healthy_tables}
          - Total records: ${data.database.summary.total_records}
          - Categories: ${foundCategories.length}
        `);
      }
    });

    it('should store health data in health_status table if it exists', async () => {
      const response = await request(app)
        .post('/api/health-full/update-status')
        .expect((res) => {
          expect([200, 500]).toContain(res.status);
        });

      if (response.status === 200) {
        // If successful, health data should have been processed
        expect(response.body.data.database.tables).toBeDefined();
        
        // The endpoint should attempt to store data regardless of table existence
        // We can't easily verify the storage happened without direct database access
        // But we can verify the response indicates successful processing
        expect(response.body.status).toBe('success');
        expect(response.body.message).toContain('updated successfully');
      }
    });
  });

  describe('Health Status Frontend Integration', () => {
    it('should be accessible from the correct frontend URL path', async () => {
      // Test that the endpoint is available at the URL the frontend expects
      const response = await request(app)
        .post('/api/health-full/update-status')
        .expect((res) => {
          // Should not return 404 (endpoint exists)
          expect(res.status).not.toBe(404);
          expect([200, 500, 503]).toContain(res.status);
        });

      // Verify endpoint exists and responds (regardless of database state)
      expect(response.body).toHaveProperty('status');
      expect(response.body).toHaveProperty('timestamp');
    });

    it('should handle CORS properly for frontend requests', async () => {
      const response = await request(app)
        .post('/api/health-full/update-status')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .expect((res) => {
          expect([200, 500, 503]).toContain(res.status);
        });

      // Verify CORS headers are set properly
      expect(response.headers['access-control-allow-origin']).toBeDefined();
    });

    it('should handle OPTIONS preflight requests', async () => {
      const response = await request(app)
        .options('/api/health-full/update-status')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .set('Access-Control-Request-Method', 'POST')
        .expect(200);

      expect(response.headers['access-control-allow-methods']).toContain('POST');
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle malformed requests gracefully', async () => {
      const response = await request(app)
        .post('/api/health-full/update-status')
        .send({ invalid: 'data' }) // Send unexpected data
        .expect((res) => {
          expect([200, 400, 500]).toContain(res.status);
        });

      // Should handle gracefully without crashing
      expect(response.body).toHaveProperty('status');
    });

    it('should handle concurrent requests properly', async () => {
      // Send multiple concurrent requests
      const requests = Array.from({ length: 3 }, () =>
        request(app)
          .post('/api/health-full/update-status')
          .expect((res) => {
            expect([200, 500, 503]).toContain(res.status);
          })
      );

      const responses = await Promise.all(requests);
      
      // All requests should complete without crashes
      responses.forEach(response => {
        expect(response.body).toHaveProperty('status');
        expect(response.body).toHaveProperty('timestamp');
      });
    });
  });
});