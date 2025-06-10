const express = require('express');
const { query, initializeDatabase, getPool } = require('../utils/database');

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    // Basic health check without database (for quick status)
    // Use ?quick=true for fast health check without database queries
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick health check - database not tested'
      });
    }// Full health check with database
    console.log('Starting health check with database...');
    
    // Initialize database if not already done
    try {
      getPool(); // This will throw if not initialized
    } catch (initError) {
      console.log('Database not initialized, initializing now...');
      await initializeDatabase();
    }
    
    // Check if database error was passed from middleware
    if (req.dbError) {
      return res.status(503).json({
        status: 'degraded',
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        database: {
          status: 'unavailable',
          error: req.dbError.message,
          lastAttempt: new Date().toISOString()
        },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    
    // Test database connection with timeout
    const dbStart = Date.now();
    const result = await Promise.race([
      query('SELECT NOW() as timestamp, version() as db_version'),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Database health check timeout')), 5000)
      )
    ]);
    const dbTime = Date.now() - dbStart;
    
    console.log(`Database connection test completed in ${dbTime}ms`);
      // Get table information (check existence first)
    let tables = {};
    try {
      const tableExistenceCheck = await Promise.race([
        query(`
          SELECT table_name 
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name IN ('company_profile', 'key_metrics', 'market_data', 'ttm_income_stmt', 'ttm_cash_flow')
        `),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Table existence check timeout')), 2000)
        )
      ]);

      const existingTables = tableExistenceCheck.rows.map(row => row.table_name);
      
      // Only count tables that exist
      if (existingTables.length > 0) {
        const countQueries = existingTables.map(tableName => 
          query(`SELECT COUNT(*) as count FROM ${tableName}`).then(result => ({
            table: tableName,
            count: parseInt(result.rows[0].count)
          })).catch(err => ({
            table: tableName,
            count: null,
            error: err.message
          }))
        );

        const tableResults = await Promise.race([
          Promise.all(countQueries),
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Table count timeout')), 5000)
          )
        ]);

        // Build tables object
        tableResults.forEach(result => {
          tables[result.table] = result.count !== null ? result.count : `Error: ${result.error}`;
        });
      }

      // Add missing tables as "not_found"
      ['company_profile', 'key_metrics', 'market_data', 'ttm_income_stmt', 'ttm_cash_flow'].forEach(tableName => {
        if (!existingTables.includes(tableName)) {
          tables[tableName] = 'not_found';
        }
      });

    } catch (tableError) {
      console.log('Table check failed:', tableError.message);
      tables = { error: tableError.message };
    }

    const health = {
      status: 'healthy',
      timestamp: result.rows[0].timestamp,
      database: {
        status: 'connected',
        version: result.rows[0].db_version.split(' ')[0],
        tables: tables
      },
      api: {
        version: '1.0.0',
        environment: process.env.NODE_ENV || 'development'
      }
    };

    res.json(health);
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      error: error.message,
      database: {
        status: 'disconnected'
      }
    });
  }
});

module.exports = router;
