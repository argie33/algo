const { query } = require('./webapp/lambda/utils/database');

(async () => {
  try {
    process.env.DB_HOST = 'localhost';
    process.env.DB_PORT = '5432';
    process.env.DB_USER = 'stocks';
    process.env.DB_PASSWORD = 'bed0elAn';
    process.env.DB_NAME = 'stocks';
    process.env.DB_SSL = 'false';

    const result = await query(`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_name = 'price_daily'
      ORDER BY ordinal_position
    `);
    
    console.log('\nPrice Daily Schema:');
    result?.rows?.forEach(r => console.log(`  ${r.column_name.padEnd(25)} ${r.data_type}`));
    console.log();
    process.exit(0);
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
})();
