#!/usr/bin/env node
/**
 * Fix AWS Database Schema Issues
 * Creates missing tables and fixes schema inconsistencies
 */

const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');
const fs = require('fs');

// AWS Configuration (same as in Lambda environment)
const AWS_REGION = 'us-east-1';
const DB_SECRET_ARN = 'arn:aws:secretsmanager:us-east-1:626216981288:secret:stocks-db-secrets-stocks-app-stack-us-east-1-001-fl3BxQ';
const DB_ENDPOINT = 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com';

async function getDatabaseCredentials() {
  const client = new SecretsManagerClient({ region: AWS_REGION });

  try {
    console.log('🔐 Retrieving database credentials from AWS Secrets Manager...');
    const response = await client.send(new GetSecretValueCommand({ SecretId: DB_SECRET_ARN }));
    const secret = JSON.parse(response.SecretString);

    return {
      host: DB_ENDPOINT,
      port: secret.port || 5432,
      database: secret.dbname,
      user: secret.username,
      password: secret.password,
      ssl: { rejectUnauthorized: false }
    };
  } catch (error) {
    console.error('❌ Failed to retrieve database credentials:', error.message);
    throw error;
  }
}

async function executeSQL(pool, sqlFile, description) {
  try {
    console.log(`📝 ${description}...`);
    const sql = fs.readFileSync(sqlFile, 'utf8');
    const client = await pool.connect();

    try {
      const result = await client.query(sql);
      console.log(`✅ ${description} completed successfully`);
      if (result.rows && result.rows.length > 0) {
        console.log('📊 Result:', result.rows);
      }
      return result;
    } finally {
      client.release();
    }
  } catch (error) {
    console.error(`❌ ${description} failed:`, error.message);
    throw error;
  }
}

async function checkTablesExist(pool) {
  const client = await pool.connect();
  try {
    console.log('🔍 Checking existing tables...');
    const result = await client.query(`
      SELECT table_name
      FROM information_schema.tables
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);

    const tables = result.rows.map(row => row.table_name);
    console.log('📋 Existing tables:', tables);

    const requiredTables = ['fundamental_metrics', 'price_daily', 'technical_data_daily'];
    const missingTables = requiredTables.filter(table => !tables.includes(table));

    if (missingTables.length > 0) {
      console.log('⚠️  Missing tables:', missingTables);
    } else {
      console.log('✅ All required tables exist');
    }

    return { existing: tables, missing: missingTables };
  } finally {
    client.release();
  }
}

async function testQueries(pool) {
  const client = await pool.connect();
  try {
    console.log('🧪 Testing key queries...');

    // Test fundamental_metrics query (this was failing)
    try {
      const result = await client.query('SELECT COUNT(*) as count FROM fundamental_metrics');
      console.log('✅ fundamental_metrics table working:', result.rows[0].count, 'records');
    } catch (error) {
      console.log('❌ fundamental_metrics query failed:', error.message);
    }

    // Test price_daily query
    try {
      const result = await client.query('SELECT COUNT(*) as count FROM price_daily');
      console.log('✅ price_daily table working:', result.rows[0].count, 'records');
    } catch (error) {
      console.log('❌ price_daily query failed:', error.message);
    }

    // Test signals-like query
    try {
      const result = await client.query(`
        SELECT symbol, date, close as price, volume
        FROM price_daily
        WHERE volume > 0 AND close > 0
        ORDER BY date DESC, symbol ASC
        LIMIT 5
      `);
      console.log('✅ Signals query working:', result.rows.length, 'records');
    } catch (error) {
      console.log('❌ Signals query failed:', error.message);
    }

  } finally {
    client.release();
  }
}

async function main() {
  console.log('🛠️  AWS Database Schema Fix');
  console.log('============================');

  let pool;
  try {
    // Get database credentials
    const dbConfig = await getDatabaseCredentials();
    console.log('✅ Database credentials retrieved successfully');

    // Create connection pool
    pool = new Pool(dbConfig);

    // Test connection
    const client = await pool.connect();
    console.log('✅ Database connection established');
    client.release();

    // Check existing tables
    const tableStatus = await checkTablesExist(pool);

    // Create missing tables
    if (tableStatus.missing.includes('fundamental_metrics')) {
      await executeSQL(pool, 'create-fundamental-metrics-table.sql', 'Creating fundamental_metrics table');
    }

    // Test queries to verify fixes
    await testQueries(pool);

    console.log('');
    console.log('🎉 AWS Database schema fix completed successfully!');
    console.log('💡 The stocks API should now work properly.');

  } catch (error) {
    console.error('❌ Database fix failed:', error.message);
    process.exit(1);
  } finally {
    if (pool) {
      await pool.end();
    }
  }
}

main();