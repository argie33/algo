const { Pool } = require('pg');

const pool = new Pool({
  host: 'localhost',
  port: 5432,
  user: 'postgres',
  password: process.env.DB_PASSWORD || '',
  database: 'stocks',
  ssl: false
});

async function test() {
  try {
    console.log('Testing database connections and data...\n');

    // Test 0: List all databases
    console.log('0. Listing all databases:');
    let result = await pool.query("SELECT datname FROM pg_database WHERE datistemplate = false");
    result.rows.forEach(row => console.log(`   - ${row.datname}`));
    console.log();

    // Test 1: Check stock_scores with composite_score > 0
    console.log('1. Checking stock_scores with composite_score > 0:');
    result = await pool.query('SELECT COUNT(*) as count FROM stock_scores WHERE composite_score > 0');
    console.log(`   Count: ${result.rows[0].count}\n`);

    // Test 2: Check all stock_scores
    console.log('2. Checking ALL stock_scores:');
    result = await pool.query('SELECT COUNT(*) as count FROM stock_scores');
    console.log(`   Count: ${result.rows[0].count}\n`);

    // Test 3: Get schema of stock_scores
    console.log('3. Schema of stock_scores table:');
    result = await pool.query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_name = 'stock_scores'
      ORDER BY ordinal_position
    `);
    result.rows.forEach(row => console.log(`   ${row.column_name}: ${row.data_type}`));
    console.log();

    // Test 4: Check other tables
    console.log('4. Checking other table counts:');
    result = await pool.query('SELECT COUNT(*) as count FROM stock_symbols');
    console.log(`   stock_symbols: ${result.rows[0].count}`);

    result = await pool.query('SELECT COUNT(*) as count FROM price_daily');
    console.log(`   price_daily: ${result.rows[0].count}`);

    result = await pool.query('SELECT COUNT(*) as count FROM company_profile');
    console.log(`   company_profile: ${result.rows[0].count}`);
    console.log();

    // Test 5: Run the actual stockscores query with EXPLAIN
    console.log('5. Running /stockscores query with EXPLAIN:');
    result = await pool.query(`
      EXPLAIN (ANALYZE, BUFFERS, TIMING)
      SELECT COUNT(*) FROM stock_scores sc
      LEFT JOIN stock_symbols ss ON ss.symbol = sc.symbol
      LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
      LEFT JOIN (
        SELECT symbol, close,
               LAG(close) OVER (PARTITION BY symbol ORDER BY date DESC) as prev_close
        FROM price_daily
      ) pd ON pd.symbol = sc.symbol
      LEFT JOIN key_metrics km ON km.symbol = sc.symbol
      LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
      LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
      WHERE sc.composite_score > 0
      LIMIT 50
    `);
    console.log('   Query plan:');
    result.rows.forEach(row => console.log('   ' + row['QUERY PLAN']));

  } catch (err) {
    console.error('Error:', err.message);
  } finally {
    await pool.end();
  }
}

test();
