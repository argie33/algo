const { Pool } = require('pg');

const pool = new Pool({
  host: 'localhost',
  port: 5432,
  user: 'stocks',
  password: 'bed0elAn',
  database: 'stocks',
  connectionTimeoutMillis: 2000,
  idleTimeoutMillis: 1000,
  max: 2
});

console.log('Connecting to PostgreSQL...');
pool.connect((err, client, release) => {
  if (err) {
    console.error('Connection error:', err.message);
    process.exit(1);
  }
  console.log('Connected! Running test query...');
  client.query('SELECT NOW()', (err, result) => {
    release();
    if (err) {
      console.error('Query error:', err.message);
    } else {
      console.log('Query succeeded:', result.rows[0]);
    }
    pool.end();
  });
});

setTimeout(() => {
  console.error('Timeout waiting for connection');
  pool.end();
  process.exit(1);
}, 5000);
