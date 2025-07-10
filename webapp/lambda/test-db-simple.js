// Simple database connection test - matches ECS pattern exactly
const { Pool } = require('pg');

const testConnection = async () => {
    console.log('🧪 Testing database connection with ECS-like config...');
    
    // Use exact same pattern as ECS tasks
    const config = {
        host: 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com',
        port: 5432,
        user: 'stocks_admin',  // Replace with actual username
        password: 'your_password_here',  // Replace with actual password
        database: 'stocks',
        ssl: false,  // No SSL like ECS
        connectionTimeoutMillis: 5000,
        max: 1  // Single connection for test
    };
    
    console.log('Config:', {
        host: config.host,
        port: config.port,
        database: config.database,
        ssl: config.ssl
    });
    
    const pool = new Pool(config);
    
    try {
        console.log('Attempting connection...');
        const client = await pool.connect();
        console.log('✅ Connected successfully!');
        
        const result = await client.query('SELECT NOW() as current_time');
        console.log('✅ Query result:', result.rows[0]);
        
        client.release();
        await pool.end();
        console.log('✅ Connection test completed successfully');
        
    } catch (error) {
        console.error('❌ Connection failed:', {
            message: error.message,
            code: error.code,
            errno: error.errno,
            syscall: error.syscall
        });
        
        await pool.end();
        throw error;
    }
};

// Run test
testConnection().catch(console.error);