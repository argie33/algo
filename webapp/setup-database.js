#!/usr/bin/env node
/**
 * Database setup script for deployment workflow
 * Creates required tables during deployment, not at runtime
 * 
 * Usage:
 *   node setup-database.js                # Check if tables exist, create only if missing
 *   node setup-database.js --force        # Force table creation regardless
 *   node setup-database.js --check-only   # Only check if tables exist, don't create
 */

const fs = require('fs');
const path = require('path');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { Pool } = require('pg');

// Configure AWS SDK
const secretsManager = new SecretsManagerClient({
    region: process.env.AWS_REGION || 'us-east-1'
});

async function getDbConfig() {
    try {
        const secretArn = process.env.DB_SECRET_ARN;
        
        if (!secretArn) {
            throw new Error('DB_SECRET_ARN environment variable is required');
        }

        console.log('Getting database credentials from Secrets Manager...');
        const command = new GetSecretValueCommand({ SecretId: secretArn });
        const result = await secretsManager.send(command);
        const secret = JSON.parse(result.SecretString);
        
        return {
            host: secret.host,
            port: parseInt(secret.port) || 5432,
            user: secret.username,
            password: secret.password,
            database: secret.dbname,
            ssl: { rejectUnauthorized: false }
        };
    } catch (error) {
        console.error('Failed to get database configuration:', error);
        throw error;
    }
}

async function executeSQL(client, sql, description) {
    try {
        console.log(`Executing: ${description}`);
        await client.query(sql);
        console.log(`✅ ${description} completed`);
    } catch (error) {
        console.error(`❌ ${description} failed:`, error.message);
        throw error;
    }
}

async function checkTablesExist(client) {
    const result = await client.query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name IN ('user_api_keys', 'portfolio_holdings', 'portfolio_metadata')
        ORDER BY table_name;
    `);
    
    const existingTables = result.rows.map(row => row.table_name);
    const requiredTables = ['user_api_keys', 'portfolio_holdings', 'portfolio_metadata'];
    
    return requiredTables.every(table => existingTables.includes(table));
}

async function setupDatabase() {
    let client = null;
    
    try {
        console.log('🚀 Starting database setup...');
        
        // Get database configuration
        const config = await getDbConfig();
        console.log(`Connecting to database: ${config.host}:${config.port}/${config.database}`);
        
        // Connect to database
        const pool = new Pool(config);
        client = await pool.connect();
        
        // Test connection
        await client.query('SELECT NOW()');
        console.log('✅ Database connection established');
        
        // Parse command line arguments
        const args = process.argv.slice(2);
        const forceCreate = args.includes('--force');
        const checkOnly = args.includes('--check-only');
        
        // Check if all required tables already exist
        const tablesExist = await checkTablesExist(client);
        
        if (checkOnly) {
            if (tablesExist) {
                console.log('✅ All required tables exist');
                process.exit(0);
            } else {
                console.log('❌ Some required tables are missing');
                process.exit(1);
            }
        }
        
        if (tablesExist && !forceCreate) {
            console.log('✅ All required tables already exist - skipping table creation');
            console.log('📊 Database setup completed successfully!');
            console.log('💡 Use --force flag to recreate tables anyway');
            return;
        }
        
        if (forceCreate) {
            console.log('🔧 Force flag detected - proceeding with table creation...');
        } else {
            console.log('🔧 Some tables missing - proceeding with table creation...');
        }
        
        // Create API Keys table
        await executeSQL(client, `
            CREATE TABLE IF NOT EXISTS user_api_keys (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                provider VARCHAR(50) NOT NULL,
                encrypted_api_key TEXT NOT NULL,
                key_iv VARCHAR(32) NOT NULL,
                key_auth_tag VARCHAR(32) NOT NULL,
                encrypted_api_secret TEXT,
                secret_iv VARCHAR(32),
                secret_auth_tag VARCHAR(32),
                user_salt VARCHAR(32) NOT NULL,
                is_sandbox BOOLEAN DEFAULT true,
                is_active BOOLEAN DEFAULT true,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_used TIMESTAMP,
                UNIQUE(user_id, provider)
            );
        `, 'Create user_api_keys table');
        
        // Create indexes for API Keys table
        await executeSQL(client, `CREATE INDEX IF NOT EXISTS idx_user_api_keys_user_id ON user_api_keys(user_id);`, 'Create user_id index');
        await executeSQL(client, `CREATE INDEX IF NOT EXISTS idx_user_api_keys_provider ON user_api_keys(provider);`, 'Create provider index');
        await executeSQL(client, `CREATE INDEX IF NOT EXISTS idx_user_api_keys_active ON user_api_keys(is_active);`, 'Create active index');
        
        // Create Portfolio Holdings table
        await executeSQL(client, `
            CREATE TABLE IF NOT EXISTS portfolio_holdings (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE CASCADE,
                symbol VARCHAR(10) NOT NULL,
                quantity DECIMAL(15, 6) NOT NULL,
                avg_cost DECIMAL(15, 4),
                current_price DECIMAL(15, 4),
                market_value DECIMAL(15, 2),
                unrealized_pl DECIMAL(15, 2),
                unrealized_plpc DECIMAL(8, 4),
                side VARCHAR(10) CHECK (side IN ('long', 'short')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, symbol, api_key_id)
            );
        `, 'Create portfolio_holdings table');
        
        // Create Portfolio Metadata table
        await executeSQL(client, `
            CREATE TABLE IF NOT EXISTS portfolio_metadata (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                api_key_id INTEGER REFERENCES user_api_keys(id) ON DELETE CASCADE,
                total_equity DECIMAL(15, 2),
                total_market_value DECIMAL(15, 2),
                total_unrealized_pl DECIMAL(15, 2),
                total_unrealized_plpc DECIMAL(8, 4),
                account_type VARCHAR(50),
                last_sync TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, api_key_id)
            );
        `, 'Create portfolio_metadata table');
        
        // Note: health_status table is created by init_health_monitoring.py script
        // It's part of the comprehensive monitoring system that tracks 70+ tables
        
        // Verify tables exist
        const tables = await client.query(`
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('user_api_keys', 'portfolio_holdings', 'portfolio_metadata')
            ORDER BY table_name;
        `);
        
        console.log('✅ Database setup completed successfully!');
        console.log(`📋 Created tables: ${tables.rows.map(r => r.table_name).join(', ')}`);
        
    } catch (error) {
        console.error('❌ Database setup failed:', error);
        process.exit(1);
    } finally {
        if (client) {
            client.release();
        }
    }
}

// Run setup if called directly
if (require.main === module) {
    setupDatabase().catch(console.error);
}

module.exports = { setupDatabase };