const { Pool } = require('pg');

const config = {
  host: 'localhost',
  port: 5432,
  user: 'postgres',
  password: 'password',
  database: 'stocks'
};

console.log('\n🔧 Testing database connection...');
console.log('Config:', { host: config.host, port: config.port, database: config.database });

const pool = new Pool(config);

pool.query('SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = \'public\'')
  .then(result => {
    console.log('✅ Connection successful!');
    console.log('📊 Tables in database:', result.rows[0].table_count);

    return pool.query('SELECT COUNT(*) as count FROM stock_scores');
  })
  .then(result => {
    console.log('📊 stock_scores records:', result.rows[0].count);

    const query = `
      SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as with_value_score,
        COUNT(CASE WHEN value_score IS NULL THEN 1 END) as without_value_score,
        COUNT(CASE WHEN momentum_score IS NULL THEN 1 END) as null_momentum,
        COUNT(CASE WHEN composite_score IS NULL THEN 1 END) as null_composite
      FROM stock_scores
    `;
    return pool.query(query);
  })
  .then(result => {
    const r = result.rows[0];
    console.log('\n📈 stock_scores data quality:');
    console.log('   Total records:', r.total);
    console.log('   With value_score:', r.with_value_score, `(${((r.with_value_score/r.total)*100).toFixed(1)}%)`);
    console.log('   NULL value_score:', r.without_value_score, `(${((r.without_value_score/r.total)*100).toFixed(1)}%)`);
    console.log('   NULL momentum_score:', r.null_momentum);
    console.log('   NULL composite_score:', r.null_composite);
  })
  .catch(err => {
    console.error('❌ Error:', err.message);
  })
  .finally(() => {
    pool.end();
  });
