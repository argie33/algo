const fs = require('fs');
const path = require('path');
const { Pool } = require('pg');

// Load environment variables
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({
  host: process.env.DB_HOST || 'localhost',
  port: process.env.DB_PORT || 5432,
  user: process.env.DB_USER || 'stocks',
  password: process.env.DB_PASSWORD,
  database: process.env.DB_NAME || 'stocks',
});

async function runSQL(filePath, description) {
  try {
    const sql = fs.readFileSync(filePath, 'utf8');
    console.log(`\n📝 Running: ${description}`);

    // Split by semicolon and filter out empty statements
    const statements = sql.split(';')
      .map(s => s.trim())
      .filter(s => s.length > 0);

    for (const statement of statements) {
      await pool.query(statement);
      console.log(`✅ Executed: ${statement.substring(0, 60)}...`);
    }
    console.log(`✅ ${description} completed successfully`);
  } catch (err) {
    console.error(`❌ Error in ${description}:`, err.message);
  }
}

async function main() {
  const files = [
    { path: './create-portfolio-tables.sql', desc: 'Portfolio tables' },
    { path: './init-db.sql', desc: 'Database initialization' },
  ];

  for (const file of files) {
    if (fs.existsSync(file.path)) {
      await runSQL(file.path, file.desc);
    } else {
      console.log(`⚠️ File not found: ${file.path}`);
    }
  }

  await pool.end();
  console.log('\n✅ All initialization scripts completed');
}

main().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
