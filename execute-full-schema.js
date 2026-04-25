const fs = require('fs');
const { Pool } = require('pg');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || 'stocks',
});

// Extract the SCHEMA from init_database.py
const pythonFile = fs.readFileSync('init_database.py', 'utf8');
const schemaMatch = pythonFile.match(/SCHEMA = """([\s\S]*?)"""/);
if (!schemaMatch) {
  console.error('❌ Could not extract SCHEMA from init_database.py');
  process.exit(1);
}

const sqlSchema = schemaMatch[1].trim();

async function initializeDatabase() {
  try {
    console.log('\n╔════════════════════════════════════════════════════════╗');
    console.log('║  Initializing Complete Database Schema                ║');
    console.log('╚════════════════════════════════════════════════════════╝\n');

    // Split by semicolon and filter out empty statements
    const statements = sqlSchema
      .split(';')
      .map(s => s.trim())
      .filter(s => s.length > 0);

    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < statements.length; i++) {
      try {
        await pool.query(statements[i]);
        console.log(`  ✓ [${String(i + 1).padStart(2, ' ')}/${statements.length}]`);
        succeeded++;
      } catch (err) {
        console.log(`  ✗ [${String(i + 1).padStart(2, ' ')}/${statements.length}] ${err.message.substring(0, 60)}`);
        failed++;
      }
    }

    console.log('\n✓ Schema initialization complete!');
    console.log(`  Succeeded: ${succeeded}`);
    console.log(`  Failed: ${failed}`);
    console.log('\nSchema is now READY for data loading\n');

    await pool.end();
    process.exit(failed > 0 ? 1 : 0);
  } catch (err) {
    console.error('❌ Fatal error:', err.message);
    await pool.end();
    process.exit(1);
  }
}

initializeDatabase();
