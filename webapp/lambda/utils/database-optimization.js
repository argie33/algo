const { query } = require('./database');

/**
 * Database optimization - Add critical indexes for performance
 */
async function createOptimizationIndexes() {
  console.log('🚀 Starting database optimization with performance indexes...');

  const indexes = [
    // Stock scores optimization - critical for scores endpoints
    {
      name: 'idx_stock_scores_symbol_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_scores_symbol_date ON stock_scores (symbol, date DESC);'
    },
    {
      name: 'idx_stock_scores_overall_score',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_scores_overall_score ON stock_scores (overall_score DESC);'
    },
    {
      name: 'idx_stock_scores_latest',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_scores_latest ON stock_scores (date DESC, overall_score DESC);'
    },

    // Price data optimization - critical for price lookups
    {
      name: 'idx_price_daily_symbol_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_daily_symbol_date ON price_daily (symbol, date DESC);'
    },
    {
      name: 'idx_price_daily_latest',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_price_daily_latest ON price_daily (date DESC);'
    },

    // Company profile optimization
    {
      name: 'idx_company_profile_ticker',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_profile_ticker ON company_profile (ticker);'
    },
    {
      name: 'idx_company_profile_sector',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_company_profile_sector ON company_profile (sector);'
    },

    // Stock symbols optimization
    {
      name: 'idx_stock_symbols_symbol',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_stock_symbols_symbol ON stock_symbols (symbol);'
    },

    // Key metrics optimization
    {
      name: 'idx_key_metrics_ticker',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_key_metrics_ticker ON key_metrics (ticker);'
    },

    // Technical data optimization
    {
      name: 'idx_technical_data_daily_symbol_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_daily_symbol_date ON technical_data_daily (symbol, date DESC);'
    },
    {
      name: 'idx_technical_data_weekly_symbol_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_weekly_symbol_date ON technical_data_weekly (symbol, date DESC);'
    },
    {
      name: 'idx_technical_data_monthly_symbol_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_technical_data_monthly_symbol_date ON technical_data_monthly (symbol, date DESC);'
    },

    // Portfolio optimization
    {
      name: 'idx_portfolio_holdings_user_symbol',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_holdings_user_symbol ON portfolio_holdings (user_id, symbol);'
    },
    {
      name: 'idx_portfolio_performance_user_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_performance_user_date ON portfolio_performance (user_id, date DESC);'
    },

    // Trade history optimization
    {
      name: 'idx_trade_history_user_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trade_history_user_date ON trade_history (user_id, trade_date DESC);'
    },
    {
      name: 'idx_trade_history_symbol_date',
      sql: 'CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_trade_history_symbol_date ON trade_history (symbol, trade_date DESC);'
    }
  ];

  let successCount = 0;
  let failureCount = 0;

  for (const index of indexes) {
    try {
      console.log(`Creating index: ${index.name}...`);
      const start = Date.now();

      await query(index.sql);

      const duration = Date.now() - start;
      console.log(`✅ Created index ${index.name} in ${duration}ms`);
      successCount++;

    } catch (error) {
      if (error.message.includes('already exists')) {
        console.log(`ℹ️  Index ${index.name} already exists, skipping`);
        successCount++;
      } else {
        console.error(`❌ Failed to create index ${index.name}:`, error.message);
        failureCount++;
      }
    }
  }

  console.log(`\n🎯 Index creation completed:`);
  console.log(`   ✅ Successful: ${successCount}`);
  console.log(`   ❌ Failed: ${failureCount}`);
  console.log(`   📊 Total: ${indexes.length}`);

  return { successCount, failureCount, total: indexes.length };
}

/**
 * Analyze slow queries and provide optimization recommendations
 */
async function analyzeQueryPerformance() {
  console.log('📊 Analyzing query performance...');

  try {
    // Check if pg_stat_statements extension is available
    const statsResult = await query(`
      SELECT COUNT(*) as count
      FROM pg_extension
      WHERE extname = 'pg_stat_statements'
    `);

    if (statsResult.rows[0].count > 0) {
      // Get slow queries from pg_stat_statements
      const slowQueries = await query(`
        SELECT
          query,
          calls,
          total_time,
          mean_time,
          rows,
          100.0 * shared_blks_hit / nullif(shared_blks_hit + shared_blks_read, 0) AS hit_percent
        FROM pg_stat_statements
        WHERE total_time > 1000  -- Queries taking more than 1 second total
        ORDER BY total_time DESC
        LIMIT 10
      `);

      console.log('Top slow queries:');
      slowQueries.rows.forEach((row, i) => {
        console.log(`${i + 1}. Mean time: ${row.mean_time.toFixed(2)}ms, Calls: ${row.calls}`);
        console.log(`   Query: ${row.query.substring(0, 100)}...`);
      });
    } else {
      console.log('pg_stat_statements extension not available for query analysis');
    }

    // Check table sizes
    const tableSizes = await query(`
      SELECT
        schemaname,
        tablename,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
        pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes
      FROM pg_tables
      WHERE schemaname = 'public'
      ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
      LIMIT 10
    `);

    console.log('\nLargest tables:');
    tableSizes.rows.forEach((row, i) => {
      console.log(`${i + 1}. ${row.tablename}: ${row.size}`);
    });

    // Check index usage
    const indexUsage = await query(`
      SELECT
        schemaname,
        tablename,
        indexname,
        idx_scan,
        idx_tup_read,
        idx_tup_fetch
      FROM pg_stat_user_indexes
      WHERE idx_scan > 0
      ORDER BY idx_scan DESC
      LIMIT 10
    `);

    console.log('\nMost used indexes:');
    indexUsage.rows.forEach((row, i) => {
      console.log(`${i + 1}. ${row.indexname}: ${row.idx_scan} scans`);
    });

  } catch (error) {
    console.error('Error analyzing query performance:', error.message);
  }
}

/**
 * Optimize database configuration for AWS RDS
 */
async function optimizeDatabaseConfig() {
  console.log('⚙️  Checking database configuration...');

  try {
    // Check current configuration settings
    const configChecks = [
      'shared_preload_libraries',
      'max_connections',
      'shared_buffers',
      'effective_cache_size',
      'work_mem',
      'maintenance_work_mem',
      'random_page_cost',
      'checkpoint_completion_target',
      'wal_buffers',
      'default_statistics_target'
    ];

    for (const setting of configChecks) {
      try {
        const result = await query(`SHOW ${setting}`);
        console.log(`${setting}: ${result.rows[0][setting]}`);
      } catch (error) {
        console.log(`${setting}: Unable to check (${error.message})`);
      }
    }

    // Provide optimization recommendations
    console.log('\n💡 Optimization recommendations:');
    console.log('1. Consider enabling pg_stat_statements for query analysis');
    console.log('2. Monitor connection pool usage and adjust max_connections if needed');
    console.log('3. Consider partitioning large tables like price_daily by date');
    console.log('4. Implement materialized views for complex aggregations');
    console.log('5. Set up automated VACUUM and ANALYZE schedules');

  } catch (error) {
    console.error('Error checking database configuration:', error.message);
  }
}

module.exports = {
  createOptimizationIndexes,
  analyzeQueryPerformance,
  optimizeDatabaseConfig
};