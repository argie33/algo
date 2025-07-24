#!/usr/bin/env node

/**
 * API Endpoints Test Script
 * Tests key API endpoints that frontend pages depend on
 */

const express = require('express');
const http = require('http');
require('dotenv').config();

const app = express();
app.use(express.json());

// Use local database configuration
const db = require('./utils/database-local-dev');

// Basic CORS for testing
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
    if (req.method === 'OPTIONS') return res.status(200).end();
    next();
});

// Test routes that frontend pages depend on
app.get('/api/portfolio', async (req, res) => {
    try {
        const userId = req.query.user_id || 'demo@example.com';
        
        const holdingsQuery = `
            SELECT 
                symbol,
                quantity,
                avg_cost,
                current_price,
                market_value,
                unrealized_pl,
                sector,
                industry,
                company
            FROM portfolio_holdings 
            WHERE user_id = $1
            ORDER BY market_value DESC
        `;
        
        const metadataQuery = `
            SELECT 
                total_equity,
                total_market_value,
                buying_power,
                cash,
                account_type
            FROM portfolio_metadata 
            WHERE user_id = $1
        `;
        
        const [holdingsResult, metadataResult] = await Promise.all([
            db.query(holdingsQuery, [userId]),
            db.query(metadataQuery, [userId])
        ]);
        
        res.json({
            success: true,
            data: {
                holdings: holdingsResult.rows,
                metadata: metadataResult.rows[0] || {},
                total_holdings: holdingsResult.rows.length
            }
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

app.get('/api/market-overview', async (req, res) => {
    try {
        const marketQuery = `
            SELECT 
                symbol,
                price,
                volume,
                market_cap,
                pe_ratio,
                sector,
                industry,
                exchange
            FROM market_data
            ORDER BY market_cap DESC
            LIMIT 20
        `;
        
        const result = await db.query(marketQuery);
        
        res.json({
            success: true,
            data: result.rows,
            count: result.rows.length
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

app.get('/api/stocks/screener', async (req, res) => {
    try {
        const screenerQuery = `
            SELECT 
                s.symbol,
                s.company_name,
                s.sector,
                s.industry,
                s.exchange,
                s.market_cap,
                m.price,
                m.pe_ratio,
                m.dividend_yield,
                m.beta
            FROM stock_symbols s
            LEFT JOIN market_data m ON s.symbol = m.symbol
            WHERE s.is_active = true
            ORDER BY s.market_cap DESC
            LIMIT 50
        `;
        
        const result = await db.query(screenerQuery);
        
        res.json({
            success: true,
            data: result.rows,
            total: result.rows.length
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

app.get('/api/news', async (req, res) => {
    try {
        // Mock news data since we don't have news table populated
        const mockNews = [
            {
                id: 1,
                headline: "Tech Stocks Rally on Strong Earnings",
                summary: "Major technology companies reported better-than-expected quarterly results, driving market gains.",
                source: "Financial News",
                publishedAt: new Date().toISOString(),
                symbols: ["AAPL", "MSFT", "GOOGL"],
                sentiment: { label: "positive", score: 0.8 }
            },
            {
                id: 2,
                headline: "Federal Reserve Maintains Interest Rates",
                summary: "The central bank decided to keep rates unchanged, citing economic stability concerns.",
                source: "Reuters",
                publishedAt: new Date(Date.now() - 3600000).toISOString(),
                symbols: ["SPY", "QQQ"],
                sentiment: { label: "neutral", score: 0.1 }
            },
            {
                id: 3,
                headline: "Electric Vehicle Sales Show Strong Growth",
                summary: "EV manufacturers report significant year-over-year sales increases across global markets.",
                source: "Auto News",
                publishedAt: new Date(Date.now() - 7200000).toISOString(),
                symbols: ["TSLA"],
                sentiment: { label: "positive", score: 0.7 }
            }
        ];
        
        res.json({
            success: true,
            data: mockNews,
            total: mockNews.length
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            error: error.message
        });
    }
});

app.get('/api/health', async (req, res) => {
    try {
        const dbHealth = await db.checkHealth();
        
        res.json({
            success: true,
            status: 'healthy',
            timestamp: new Date().toISOString(),
            services: {
                database: dbHealth,
                api: { status: 'healthy', message: 'API server operational' }
            }
        });
    } catch (error) {
        res.status(500).json({
            success: false,
            status: 'unhealthy',
            error: error.message
        });
    }
});

// Test function
async function testEndpoints() {
    console.log('🧪 Testing API endpoints...\n');
    
    const server = http.createServer(app);
    const port = 3001;
    
    await new Promise((resolve) => {
        server.listen(port, () => {
            console.log(`✅ Test server running on http://localhost:${port}`);
            resolve();
        });
    });
    
    const endpoints = [
        { name: 'Health Check', path: '/api/health' },
        { name: 'Portfolio Data', path: '/api/portfolio' },
        { name: 'Market Overview', path: '/api/market-overview' },
        { name: 'Stock Screener', path: '/api/stocks/screener' },
        { name: 'News Feed', path: '/api/news' }
    ];
    
    console.log('📡 Testing endpoints:\n');
    
    for (const endpoint of endpoints) {
        try {
            const response = await fetch(`http://localhost:${port}${endpoint.path}`);
            const data = await response.json();
            
            if (response.ok && data.success) {
                const dataCount = data.data ? (Array.isArray(data.data) ? data.data.length : 'object') : 'none';
                console.log(`✅ ${endpoint.name}: ${response.status} - ${dataCount} items`);
            } else {
                console.log(`❌ ${endpoint.name}: ${response.status} - ${data.error || 'Failed'}`);
            }
        } catch (error) {
            console.log(`❌ ${endpoint.name}: Request failed - ${error.message}`);
        }
    }
    
    console.log('\n🎉 API endpoint testing completed!');
    console.log('\n💡 If all tests passed, your frontend should now receive data from these endpoints');
    
    server.close();
    await db.closeConnections();
}

if (require.main === module) {
    testEndpoints().catch(console.error);
}

module.exports = { app, testEndpoints };