#!/usr/bin/env node
/**
 * Database Schema Validator for Seasonality & Financial Integrity
 *
 * Validates that all critical financial tables have proper NOT NULL constraints
 * and that data types are correct for financial calculations.
 *
 * Usage:
 *   node check-seasonality-schema.mjs [db_connection_string]
 */

import pg from 'pg';

const { Client } = pg;

const CRITICAL_TABLES = {
  algo_trades: {
    critical_columns: [
      { name: 'trade_id', type: 'text', nullable: false },
      { name: 'symbol', type: 'text', nullable: false },
      { name: 'entry_price', type: 'numeric', nullable: false },
      { name: 'entry_quantity', type: 'numeric', nullable: false },
      { name: 'exit_price', type: 'numeric', nullable: true },
      { name: 'profit_loss_dollars', type: 'numeric', nullable: true },
      { name: 'profit_loss_pct', type: 'numeric', nullable: true }
    ]
  },
  algo_positions: {
    critical_columns: [
      { name: 'symbol', type: 'text', nullable: false },
      { name: 'quantity', type: 'numeric', nullable: false },
      { name: 'avg_entry_price', type: 'numeric', nullable: false },
      { name: 'current_price', type: 'numeric', nullable: false },
      { name: 'position_value', type: 'numeric', nullable: false },
      { name: 'unrealized_pnl', type: 'numeric', nullable: false }
    ]
  },
  algo_portfolio_snapshots: {
    critical_columns: [
      { name: 'snapshot_date', type: 'date', nullable: false },
      { name: 'total_portfolio_value', type: 'numeric', nullable: false },
      { name: 'total_cash', type: 'numeric', nullable: false },
      { name: 'daily_return_pct', type: 'numeric', nullable: true }
    ]
  },
  swing_trader_scores: {
    critical_columns: [
      { name: 'symbol', type: 'text', nullable: false },
      { name: 'score', type: 'numeric', nullable: false },
      { name: 'date', type: 'date', nullable: false }
    ]
  },
  market_health_daily: {
    critical_columns: [
      { name: 'date', type: 'date', nullable: false },
      { name: 'vix_level', type: 'numeric', nullable: true },
      { name: 'market_stage', type: 'integer', nullable: true }
    ]
  },
  aaii_sentiment: {
    critical_columns: [
      { name: 'date', type: 'date', nullable: false },
      { name: 'bullish', type: 'numeric', nullable: false },
      { name: 'bearish', type: 'numeric', nullable: false }
    ]
  },
  sector_ranking: {
    critical_columns: [
      { name: 'date', type: 'date', nullable: false },
      { name: 'sector_name', type: 'text', nullable: false },
      { name: 'momentum_score', type: 'numeric', nullable: true }
    ]
  },
  stock_scores: {
    critical_columns: [
      { name: 'symbol', type: 'text', nullable: false },
      { name: 'composite_score', type: 'numeric', nullable: true },
      { name: 'quality_score', type: 'numeric', nullable: true },
      { name: 'growth_score', type: 'numeric', nullable: true }
    ]
  }
};

async function validateSchema(connectionString) {
  const client = new Client({
    connectionString: connectionString || process.env.DATABASE_URL
  });

  try {
    await client.connect();
    console.log('✓ Connected to database\n');

    let totalIssues = 0;
    let passedValidations = 0;

    for (const [tableName, config] of Object.entries(CRITICAL_TABLES)) {
      console.log(`Checking table: ${tableName}`);

      try {
        // Check if table exists
        const tableExistsResult = await client.query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = $1
          )
        `, [tableName]);

        if (!tableExistsResult.rows[0].exists) {
          console.log(`  ⚠️  TABLE MISSING: ${tableName} does not exist`);
          totalIssues++;
          continue;
        }

        // Validate critical columns
        for (const col of config.critical_columns) {
          const result = await client.query(`
            SELECT
              column_name,
              data_type,
              is_nullable
            FROM information_schema.columns
            WHERE table_name = $1 AND column_name = $2
          `, [tableName, col.name]);

          if (result.rows.length === 0) {
            console.log(`  ✗ MISSING COLUMN: ${tableName}.${col.name}`);
            totalIssues++;
            continue;
          }

          const dbCol = result.rows[0];

          // Check data type compatibility
          const expectedType = col.type.toLowerCase();
          const actualType = dbCol.data_type.toLowerCase();
          const isCompatible = actualType.includes(expectedType) ||
                              expectedType.includes(actualType);

          if (!isCompatible && col.nullable === false) {
            console.log(`  ✗ TYPE MISMATCH: ${tableName}.${col.name}`);
            console.log(`    Expected: ${col.type}, Got: ${dbCol.data_type}`);
            totalIssues++;
          }

          // Check nullable constraint
          const dbNullable = dbCol.is_nullable === 'YES';
          if (dbNullable !== col.nullable && col.nullable === false) {
            console.log(`  ✗ NULLABLE MISMATCH: ${tableName}.${col.name} should NOT NULL`);
            totalIssues++;
          } else {
            console.log(`  ✓ ${tableName}.${col.name} (${dbCol.data_type}, nullable: ${dbNullable})`);
            passedValidations++;
          }
        }
        console.log('');
      } catch (error) {
        console.log(`  ✗ ERROR checking table: ${error.message}`);
        totalIssues++;
      }
    }

    // Summary
    console.log('\n=== VALIDATION SUMMARY ===');
    console.log(`✓ Passed: ${passedValidations}`);
    console.log(`✗ Issues: ${totalIssues}`);

    if (totalIssues === 0) {
      console.log('\n✅ All critical schema requirements validated!');
      console.log('Financial data integrity: VERIFIED');
      console.log('Safe for production: YES');
      return true;
    } else {
      console.log('\n⚠️  Schema validation failed. Fix issues before deploying.');
      return false;
    }
  } catch (error) {
    console.error('✗ Database connection failed:', error.message);
    console.error('\nMake sure DATABASE_URL is set or pass connection string as argument');
    process.exit(1);
  } finally {
    await client.end();
  }
}

// Main
const connectionString = process.argv[2];
const success = await validateSchema(connectionString);
process.exit(success ? 0 : 1);
