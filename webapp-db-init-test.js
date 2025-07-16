#!/usr/bin/env node
/**
 * TEST: Database connection with multiple SSL configurations
 */

const { Client } = require('pg');

// Test database connection with different SSL configurations
async function testDatabaseConnection() {
    const baseConfig = {
        host: 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com',
        port: 5432,
        database: 'stocks',
        user: 'stocks',
        password: process.env.DB_PASSWORD || '',
        connectionTimeoutMillis: 30000,
        query_timeout: 30000,
        statement_timeout: 30000
    };

    const sslConfigs = [
        { ssl: false, name: 'No SSL' },
        { ssl: { rejectUnauthorized: false }, name: 'SSL without verification' },
        { ssl: true, name: 'SSL with defaults' }
    ];

    console.log('Testing database connection with different SSL configurations...');
    
    for (const sslConfig of sslConfigs) {
        const config = { ...baseConfig, ssl: sslConfig.ssl };
        console.log(`\nTesting: ${sslConfig.name}`);
        
        try {
            const client = new Client(config);
            
            const startTime = Date.now();
            await client.connect();
            const connectTime = Date.now() - startTime;
            
            console.log(`✅ Connection successful in ${connectTime}ms`);
            
            // Test query
            const result = await client.query('SELECT current_database(), current_user');
            console.log(`   Database: ${result.rows[0].current_database}`);
            console.log(`   User: ${result.rows[0].current_user}`);
            
            await client.end();
            console.log('✅ Test completed successfully');
            return true;
            
        } catch (error) {
            console.log(`❌ Failed: ${error.message}`);
            console.log(`   Code: ${error.code}`);
        }
    }
    
    console.log('\n❌ All connection methods failed');
    return false;
}

// Run the test
testDatabaseConnection().catch(console.error);