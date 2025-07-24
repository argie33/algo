#!/usr/bin/env node

/**
 * Database Connection Test
 * 
 * This script tests the database connection and checks for loadinfo data
 * to verify Stock Explorer will show real data instead of mock data.
 */

require('dotenv').config();

async function testDatabaseConnection() {
    console.log('🧪 Database Connection Test');
    console.log('===========================');
    console.log('');
    
    try {
        // Import database utilities
        const { query } = require('./utils/database');
        
        console.log('📊 Testing database connection and checking loadinfo data...');
        console.log('');
        
        // Test 1: Basic connection
        console.log('Test 1: Basic Connection');
        console.log('========================');
        const basicTest = await query('SELECT 1 as test', [], 5000);
        console.log('✅ Database connection successful');
        console.log('');
        
        // Test 2: Check stock_symbols table
        console.log('Test 2: Stock Symbols Table');
        console.log('============================');
        try {
            const stockSymbolsCount = await query('SELECT COUNT(*) as count FROM stock_symbols WHERE is_active = TRUE');
            const totalSymbols = parseInt(stockSymbolsCount.rows[0].count);
            console.log(`✅ stock_symbols table exists with ${totalSymbols} active symbols`);
            
            if (totalSymbols > 10) {
                console.log('✅ Good! You have more than the 10 mock stocks');
            } else {
                console.log('⚠️  Warning: Only 10 or fewer stocks found - may still be using mock data');
            }
        } catch (error) {
            console.log('❌ stock_symbols table missing or inaccessible:', error.message);
        }
        console.log('');
        
        // Test 3: Check loadinfo tables
        console.log('Test 3: Loadinfo Tables');
        console.log('========================');
        const loadinfoTables = [
            'symbols',
            'market_data', 
            'key_metrics',
            'analyst_estimates',
            'governance_scores'
        ];
        
        for (const tableName of loadinfoTables) {
            try {
                const result = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
                const count = parseInt(result.rows[0].count);
                console.log(`✅ ${tableName}: ${count} records`);
            } catch (error) {
                console.log(`❌ ${tableName}: table missing or inaccessible`);
            }
        }
        console.log('');
        
        // Test 4: Sample of real data
        console.log('Test 4: Sample Real Data');
        console.log('=========================');
        try {
            const sampleQuery = `
                SELECT 
                    s.symbol,
                    s.long_name,
                    md.current_price,
                    km.trailing_pe,
                    ae.target_mean_price
                FROM symbols s
                LEFT JOIN market_data md ON s.symbol = md.ticker
                LEFT JOIN key_metrics km ON s.symbol = km.ticker  
                LEFT JOIN analyst_estimates ae ON s.symbol = ae.ticker
                WHERE s.symbol NOT IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'AMZN', 'NVDA', 'META', 'BRK.A', 'JNJ', 'V')
                LIMIT 5
            `;
            
            const sampleResult = await query(sampleQuery);
            
            if (sampleResult.rows.length > 0) {
                console.log('✅ Found real loadinfo data (non-mock symbols):');
                console.table(sampleResult.rows);
                console.log('🎉 SUCCESS: Your database contains real loadinfo data!');
                console.log('   Stock Explorer should now show this data instead of mock data.');
            } else {
                console.log('⚠️  No non-mock symbols found in loadinfo tables');
                console.log('   Stock Explorer may still show mock data');
            }
        } catch (error) {
            console.log('❌ Error checking sample data:', error.message);
        }
        console.log('');
        
        // Test 5: Check /screen endpoint behavior
        console.log('Test 5: API Endpoint Test');
        console.log('==========================');
        console.log('Testing the Stock Explorer /screen endpoint...');
        
        // Simulate the screen endpoint logic
        try {
            // Test database connectivity (like the /screen endpoint does)
            await query('SELECT 1 as test', [], 5000);
            console.log('✅ Database test passed - /screen endpoint will use REAL data');
            console.log('');
            
            // Show what the screen endpoint would return
            const screenQuery = `
                SELECT COUNT(*) as total
                FROM stock_symbols ss
                LEFT JOIN symbols s ON ss.symbol = s.symbol
                WHERE ss.is_active = TRUE
            `;
            
            const screenResult = await query(screenQuery);
            const totalScreenStocks = parseInt(screenResult.rows[0].total);
            
            console.log(`📊 Stock Explorer will show ${totalScreenStocks} stocks total`);
            
            if (totalScreenStocks > 10) {
                console.log('🎉 SUCCESS: Stock Explorer will show REAL data from your loadinfo script!');
            } else {
                console.log('⚠️  Warning: Only 10 stocks available - may be limited dataset');
            }
            
        } catch (dbError) {
            console.log('❌ Database test failed - /screen endpoint will use MOCK data');
            console.log('   Error:', dbError.message);
        }
        
        console.log('');
        console.log('🔧 Next steps:');
        console.log('1. If tests passed: Restart your API server');
        console.log('2. Open Stock Explorer in your browser');
        console.log('3. You should see real data instead of just AAPL, MSFT, GOOGL, etc.');
        console.log('4. If still showing mock data, check server logs for database connection errors');
        
    } catch (error) {
        console.error('❌ Database connection test failed:', error.message);
        console.log('');
        console.log('🔧 Troubleshooting:');
        console.log('1. Check your .env.local file has correct database credentials');
        console.log('2. Ensure NODE_ENV=development');
        console.log('3. Verify database is accessible from this machine');
        console.log('4. Run: node setup-database-connection.js for help');
    }
}

// Run the test
testDatabaseConnection();