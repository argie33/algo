/**
 * AI Database Setup Lambda
 * Creates and manages AI-specific database tables and indexes
 */

const { Client } = require('pg');

/**
 * Main Lambda handler
 */
exports.handler = async (event) => {
  console.log('🗄️ Setting up AI agent database tables...');
  console.log('Event:', JSON.stringify(event, null, 2));
  
  const client = new Client({
    host: process.env.DATABASE_ENDPOINT.split(':')[0],
    port: 5432,
    database: 'stocks_db',
    user: 'stocks_user',
    // Password would come from secrets manager in real implementation
    ssl: process.env.NODE_ENV === 'production'
  });
  
  try {
    await client.connect();
    console.log('✅ Connected to database');
    
    // Determine action based on event
    const action = event.action || 'setup';
    
    switch (action) {
      case 'setup':
        await setupAITables(client);
        break;
      case 'upgrade':
        await upgradeAITables(client);
        break;
      case 'cleanup':
        await cleanupAITables(client);
        break;
      default:
        throw new Error(`Unknown action: ${action}`);
    }
    
    await client.end();
    console.log('✅ Database setup completed successfully');
    
    return {
      statusCode: 200,
      body: JSON.stringify({ 
        success: true, 
        message: `AI database ${action} completed successfully`,
        timestamp: new Date().toISOString()
      })
    };
    
  } catch (error) {
    console.error('❌ Database setup error:', error);
    
    try {
      await client.end();
    } catch (closeError) {
      console.error('Error closing connection:', closeError);
    }
    
    return {
      statusCode: 500,
      body: JSON.stringify({
        success: false,
        error: error.message,
        timestamp: new Date().toISOString()
      })
    };
  }
};

/**
 * Setup AI-specific database tables
 */
async function setupAITables(client) {
  console.log('📋 Creating AI conversation tables...');
  
  // Enhanced conversations table with encryption and threading support
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_conversations_enhanced (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      conversation_id VARCHAR(255) NOT NULL,
      message_id BIGINT NOT NULL,
      parent_message_id BIGINT,
      thread_id VARCHAR(255),
      message_type VARCHAR(20) NOT NULL CHECK (message_type IN ('user', 'assistant', 'system')),
      content TEXT NOT NULL,
      content_encrypted BOOLEAN DEFAULT FALSE,
      suggestions JSONB,
      context JSONB,
      metadata JSONB,
      token_count INTEGER DEFAULT 0,
      model_used VARCHAR(100),
      response_time_ms INTEGER,
      sentiment_score DECIMAL(3,2),
      timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  // Create indexes for performance
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_conversations_user_conv_time 
    ON ai_conversations_enhanced(user_id, conversation_id, timestamp);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_conversations_user_time 
    ON ai_conversations_enhanced(user_id, timestamp);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_conversations_message_id 
    ON ai_conversations_enhanced(conversation_id, message_id);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_conversations_thread 
    ON ai_conversations_enhanced(thread_id) WHERE thread_id IS NOT NULL;
  `);
  
  // Unique constraint for message IDs within conversations
  await client.query(`
    CREATE UNIQUE INDEX IF NOT EXISTS uk_ai_conversations_message 
    ON ai_conversations_enhanced(user_id, conversation_id, message_id);
  `);
  
  console.log('✅ AI conversations table created');
  
  // Enhanced conversation metadata table
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_conversation_metadata (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      conversation_id VARCHAR(255) NOT NULL,
      title VARCHAR(500),
      summary TEXT,
      tags TEXT[],
      context JSONB,
      total_messages INTEGER DEFAULT 0,
      total_tokens INTEGER DEFAULT 0,
      average_response_time INTEGER,
      satisfaction_score DECIMAL(3,2),
      last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  await client.query(`
    CREATE UNIQUE INDEX IF NOT EXISTS uk_ai_conversation_metadata 
    ON ai_conversation_metadata(user_id, conversation_id);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_conversation_metadata_activity 
    ON ai_conversation_metadata(user_id, last_activity);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_conversation_metadata_tags 
    ON ai_conversation_metadata USING GIN(tags);
  `);
  
  console.log('✅ AI conversation metadata table created');
  
  // User AI configurations table
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_user_configurations (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255) UNIQUE NOT NULL,
      preferred_model VARCHAR(100) DEFAULT 'claude-3-haiku',
      response_style VARCHAR(50) DEFAULT 'balanced',
      max_tokens INTEGER DEFAULT 1000,
      temperature DECIMAL(3,2) DEFAULT 0.1,
      streaming_enabled BOOLEAN DEFAULT TRUE,
      conversation_history_enabled BOOLEAN DEFAULT TRUE,
      analytics_enabled BOOLEAN DEFAULT TRUE,
      custom_instructions TEXT,
      language_preference VARCHAR(10) DEFAULT 'en',
      timezone VARCHAR(50),
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_user_configurations_user 
    ON ai_user_configurations(user_id);
  `);
  
  console.log('✅ AI user configurations table created');
  
  // Conversation analytics table
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_conversation_analytics (
      id SERIAL PRIMARY KEY,
      conversation_id VARCHAR(255) NOT NULL,
      user_id VARCHAR(255) NOT NULL,
      session_duration INTEGER,
      message_count INTEGER,
      total_tokens INTEGER,
      average_tokens_per_message DECIMAL(10,2),
      topics TEXT[],
      sentiment_score DECIMAL(3,2),
      satisfaction_score INTEGER CHECK (satisfaction_score >= 1 AND satisfaction_score <= 5),
      cost_estimate DECIMAL(10,4),
      model_usage JSONB,
      interaction_patterns JSONB,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_analytics_user_date 
    ON ai_conversation_analytics(user_id, created_at);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_analytics_conversation 
    ON ai_conversation_analytics(conversation_id);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_analytics_topics 
    ON ai_conversation_analytics USING GIN(topics);
  `);
  
  console.log('✅ AI conversation analytics table created');
  
  // WebSocket connections table
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_websocket_connections (
      id SERIAL PRIMARY KEY,
      connection_id VARCHAR(255) UNIQUE NOT NULL,
      user_id VARCHAR(255) NOT NULL,
      user_agent TEXT,
      ip_address INET,
      connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      disconnected_at TIMESTAMP WITH TIME ZONE,
      last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_websocket_user 
    ON ai_websocket_connections(user_id);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_websocket_active 
    ON ai_websocket_connections(connected_at) WHERE disconnected_at IS NULL;
  `);
  
  console.log('✅ AI WebSocket connections table created');
  
  // Streaming sessions table
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_streaming_sessions (
      id SERIAL PRIMARY KEY,
      session_id VARCHAR(255) UNIQUE NOT NULL,
      connection_id VARCHAR(255) NOT NULL,
      user_id VARCHAR(255) NOT NULL,
      conversation_id VARCHAR(255) NOT NULL,
      message_id BIGINT NOT NULL,
      status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'failed', 'cancelled', 'disconnected')),
      started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
      ended_at TIMESTAMP WITH TIME ZONE,
      duration_ms INTEGER,
      tokens_streamed INTEGER DEFAULT 0,
      chunks_sent INTEGER DEFAULT 0,
      error_message TEXT
    );
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_streaming_connection 
    ON ai_streaming_sessions(connection_id);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_streaming_user 
    ON ai_streaming_sessions(user_id, started_at);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_streaming_status 
    ON ai_streaming_sessions(status, started_at);
  `);
  
  console.log('✅ AI streaming sessions table created');
  
  // User typing status table
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_user_typing_status (
      connection_id VARCHAR(255) PRIMARY KEY,
      user_id VARCHAR(255) NOT NULL,
      conversation_id VARCHAR(255),
      is_typing BOOLEAN DEFAULT FALSE,
      updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_typing_user 
    ON ai_user_typing_status(user_id);
  `);
  
  console.log('✅ AI typing status table created');
  
  // AI model usage tracking
  await client.query(`
    CREATE TABLE IF NOT EXISTS ai_model_usage (
      id SERIAL PRIMARY KEY,
      user_id VARCHAR(255),
      model_id VARCHAR(100) NOT NULL,
      input_tokens INTEGER DEFAULT 0,
      output_tokens INTEGER DEFAULT 0,
      total_requests INTEGER DEFAULT 1,
      cost_estimate DECIMAL(10,4),
      date DATE DEFAULT CURRENT_DATE,
      created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_model_usage_user_date 
    ON ai_model_usage(user_id, date);
  `);
  
  await client.query(`
    CREATE INDEX IF NOT EXISTS idx_ai_model_usage_model_date 
    ON ai_model_usage(model_id, date);
  `);
  
  console.log('✅ AI model usage table created');
  
  // Create triggers for updating timestamps
  await client.query(`
    CREATE OR REPLACE FUNCTION update_ai_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
      NEW.updated_at = NOW();
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
  `);
  
  // Apply triggers to relevant tables
  const tablesWithUpdatedAt = [
    'ai_conversations_enhanced',
    'ai_conversation_metadata', 
    'ai_user_configurations'
  ];
  
  for (const table of tablesWithUpdatedAt) {
    await client.query(`
      DROP TRIGGER IF EXISTS trigger_update_${table}_updated_at ON ${table};
      CREATE TRIGGER trigger_update_${table}_updated_at
        BEFORE UPDATE ON ${table}
        FOR EACH ROW
        EXECUTE FUNCTION update_ai_updated_at();
    `);
  }
  
  console.log('✅ Triggers created for timestamp updates');
  
  // Create view for conversation summaries
  await client.query(`
    CREATE OR REPLACE VIEW ai_conversation_summaries AS
    SELECT 
      m.user_id,
      m.conversation_id,
      m.title,
      m.total_messages,
      m.total_tokens,
      m.last_activity,
      m.created_at,
      COALESCE(
        (SELECT content FROM ai_conversations_enhanced c 
         WHERE c.user_id = m.user_id 
         AND c.conversation_id = m.conversation_id 
         AND c.message_type = 'user'
         ORDER BY c.timestamp ASC LIMIT 1),
        'No messages'
      ) as first_message,
      COALESCE(
        (SELECT content FROM ai_conversations_enhanced c 
         WHERE c.user_id = m.user_id 
         AND c.conversation_id = m.conversation_id 
         ORDER BY c.timestamp DESC LIMIT 1),
        'No messages'
      ) as last_message
    FROM ai_conversation_metadata m;
  `);
  
  console.log('✅ AI conversation summaries view created');
  
  console.log('🎉 All AI database tables and indexes created successfully');
}

/**
 * Upgrade existing AI tables with new features
 */
async function upgradeAITables(client) {
  console.log('⬆️ Upgrading AI database tables...');
  
  // Add any new columns or modifications here
  try {
    // Example: Add new column if it doesn't exist
    await client.query(`
      ALTER TABLE ai_conversations_enhanced 
      ADD COLUMN IF NOT EXISTS sentiment_score DECIMAL(3,2);
    `);
    
    await client.query(`
      ALTER TABLE ai_user_configurations 
      ADD COLUMN IF NOT EXISTS language_preference VARCHAR(10) DEFAULT 'en';
    `);
    
    await client.query(`
      ALTER TABLE ai_user_configurations 
      ADD COLUMN IF NOT EXISTS timezone VARCHAR(50);
    `);
    
    console.log('✅ AI tables upgraded successfully');
  } catch (error) {
    console.error('❌ Error upgrading tables:', error);
    throw error;
  }
}

/**
 * Clean up AI tables (for development/testing)
 */
async function cleanupAITables(client) {
  console.log('🧹 Cleaning up AI database tables...');
  
  if (process.env.NODE_ENV === 'production') {
    throw new Error('Cleanup not allowed in production environment');
  }
  
  const tables = [
    'ai_model_usage',
    'ai_user_typing_status',
    'ai_streaming_sessions',
    'ai_websocket_connections',
    'ai_conversation_analytics',
    'ai_user_configurations',
    'ai_conversation_metadata',
    'ai_conversations_enhanced'
  ];
  
  for (const table of tables) {
    try {
      await client.query(`DROP TABLE IF EXISTS ${table} CASCADE;`);
      console.log(`✅ Dropped table: ${table}`);
    } catch (error) {
      console.error(`❌ Error dropping table ${table}:`, error);
    }
  }
  
  // Drop view
  await client.query(`DROP VIEW IF EXISTS ai_conversation_summaries;`);
  
  // Drop function
  await client.query(`DROP FUNCTION IF EXISTS update_ai_updated_at() CASCADE;`);
  
  console.log('✅ AI tables cleanup completed');
}