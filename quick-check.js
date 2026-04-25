const pg = require('pg');

const config = {
  host: 'localhost',
  port: 5432,
  user: 'stocks',
  password: 'bed0elAn',
  database: 'stocks'
};

const client = new pg.Client(config);

async function check() {
  try {
    await client.connect();
    
    const tables = ['stock_scores', 'stock_symbols', 'earnings_history', 'earnings_estimates', 'daily_prices'];
    
    console.log('Table Status:');
    for (const tbl of tables) {
      try {
        const res = await client.query(`SELECT COUNT(*) FROM ${tbl}`);
        console.log(`  ${tbl}: ${res.rows[0].count} rows`);
      } catch (e) {
        console.log(`  ${tbl}: ERROR - ${e.message.split('\n')[0]}`);
      }
    }
    
  } finally {
    await client.end();
  }
}

check();
