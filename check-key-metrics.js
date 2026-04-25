const { query } = require('./webapp/lambda/utils/database');
process.env.DB_HOST = 'localhost';
process.env.DB_PORT = '5432';
process.env.DB_USER = 'stocks';
process.env.DB_PASSWORD = 'bed0elAn';
process.env.DB_NAME = 'stocks';
process.env.DB_SSL = 'false';

(async () => {
  try {
    const result = await query(`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_name = 'key_metrics'
      ORDER BY ordinal_position
      LIMIT 20
    `, []);
    console.log('Key Metrics Columns:');
    result?.rows?.forEach(r => {
      console.log(`  ${r.column_name.padEnd(30)} ${r.data_type}`);
    });
    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
})();
