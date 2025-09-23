const { query } = require('./utils/database');

async function createSignalAlertsTable() {
  console.log('🔧 Creating signal_alerts table...');

  try {
    const createTableQuery = `
      CREATE TABLE IF NOT EXISTS signal_alerts (
        alert_id VARCHAR(100) PRIMARY KEY,
        symbol VARCHAR(10) NOT NULL,
        signal_type VARCHAR(10) DEFAULT 'BUY',
        min_strength DECIMAL(3,2) DEFAULT 0.7,
        notification_method VARCHAR(20) DEFAULT 'email',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status VARCHAR(20) DEFAULT 'active'
      )
    `;

    await query(createTableQuery);
    console.log('✅ signal_alerts table created successfully');

    // Insert some sample data
    const sampleData = [
      ['alert_sample_1', 'AAPL', 'BUY', 0.8, 'email', new Date(), 'active'],
      ['alert_sample_2', 'TSLA', 'SELL', 0.7, 'sms', new Date(), 'active'],
      ['alert_sample_3', 'MSFT', 'BUY', 0.9, 'email', new Date(), 'active']
    ];

    for (const alert of sampleData) {
      const insertQuery = `
        INSERT INTO signal_alerts (alert_id, symbol, signal_type, min_strength, notification_method, created_at, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (alert_id) DO NOTHING
      `;
      await query(insertQuery, alert);
    }

    console.log('✅ Sample signal alerts inserted');

    // Verify the table was created
    const verifyQuery = `SELECT COUNT(*) as count FROM signal_alerts`;
    const result = await query(verifyQuery);
    console.log(`📊 signal_alerts table contains ${result.rows[0].count} records`);

  } catch (error) {
    console.error('❌ Error creating signal_alerts table:', error);
    throw error;
  }
}

if (require.main === module) {
  createSignalAlertsTable()
    .then(() => {
      console.log('🎉 Signal alerts table setup complete');
      process.exit(0);
    })
    .catch(error => {
      console.error('💥 Failed to create signal_alerts table:', error);
      process.exit(1);
    });
}

module.exports = createSignalAlertsTable;