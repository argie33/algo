/**
 * Conversation Store - Database-backed conversation persistence
 * 
 * Provides persistent conversation storage with fallback to in-memory
 * for when database is unavailable
 */

const { query } = require('./database');

class ConversationStore {
  constructor() {
    // In-memory fallback for when database is unavailable
    this.memoryStore = new Map();
    this.dbAvailable = null; // null = unknown, true = available, false = unavailable
    this.lastDbCheck = 0;
    this.dbCheckInterval = 30000; // Check every 30 seconds
  }

  /**
   * Check if database is available
   */
  async checkDatabaseAvailability() {
    const now = Date.now();
    if (this.dbAvailable !== null && (now - this.lastDbCheck) < this.dbCheckInterval) {
      return this.dbAvailable;
    }

    try {
      await query('SELECT 1 as test');
      this.dbAvailable = true;
      this.lastDbCheck = now;
      console.log('✅ Database available for conversation storage');
      return true;
    } catch (error) {
      this.dbAvailable = false;
      this.lastDbCheck = now;
      console.log('⚠️ Database unavailable, using memory storage for conversations');
      return false;
    }
  }

  /**
   * Initialize conversation tables if needed
   */
  async initializeTables() {
    try {
      await query(`
        CREATE TABLE IF NOT EXISTS ai_conversations (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          conversation_id VARCHAR(255) NOT NULL,
          message_id BIGINT NOT NULL,
          message_type VARCHAR(20) NOT NULL CHECK (message_type IN ('user', 'assistant')),
          content TEXT NOT NULL,
          suggestions JSONB,
          context JSONB,
          timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          
          INDEX(user_id, conversation_id, timestamp),
          INDEX(user_id, timestamp),
          UNIQUE(user_id, conversation_id, message_id)
        )
      `);

      await query(`
        CREATE TABLE IF NOT EXISTS ai_conversation_metadata (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          conversation_id VARCHAR(255) NOT NULL,
          title VARCHAR(500),
          summary TEXT,
          total_messages INTEGER DEFAULT 0,
          last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          
          UNIQUE(user_id, conversation_id),
          INDEX(user_id, last_activity)
        )
      `);

      console.log('✅ AI conversation tables initialized');
      return true;
    } catch (error) {
      console.error('❌ Failed to initialize conversation tables:', error.message);
      return false;
    }
  }

  /**
   * Add message to conversation
   */
  async addMessage(userId, conversationId, message) {
    const dbAvailable = await this.checkDatabaseAvailability();
    
    if (dbAvailable) {
      try {
        // Store in database
        await query(`
          INSERT INTO ai_conversations (
            user_id, conversation_id, message_id, message_type, 
            content, suggestions, context, timestamp
          ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
          ON CONFLICT (user_id, conversation_id, message_id) 
          DO UPDATE SET 
            content = EXCLUDED.content,
            suggestions = EXCLUDED.suggestions,
            context = EXCLUDED.context,
            timestamp = EXCLUDED.timestamp
        `, [
          userId,
          conversationId,
          message.id,
          message.type,
          message.content,
          JSON.stringify(message.suggestions || []),
          JSON.stringify(message.context || {}),
          message.timestamp || new Date()
        ]);

        // Update conversation metadata
        await query(`
          INSERT INTO ai_conversation_metadata (
            user_id, conversation_id, total_messages, last_activity
          ) VALUES ($1, $2, 1, NOW())
          ON CONFLICT (user_id, conversation_id)
          DO UPDATE SET 
            total_messages = ai_conversation_metadata.total_messages + 1,
            last_activity = NOW()
        `, [userId, conversationId]);

        console.log(`✅ Message stored in database for user ${userId}`);
        return true;
      } catch (error) {
        console.error('❌ Failed to store message in database:', error.message);
        // Fallback to memory storage
        this.dbAvailable = false;
      }
    }

    // Fallback to in-memory storage
    return this.addMessageToMemory(userId, conversationId, message);
  }

  /**
   * Get conversation history
   */
  async getHistory(userId, conversationId, limit = 50, offset = 0) {
    const dbAvailable = await this.checkDatabaseAvailability();
    
    if (dbAvailable) {
      try {
        const result = await query(`
          SELECT 
            message_id as id,
            message_type as type,
            content,
            suggestions,
            context,
            timestamp
          FROM ai_conversations 
          WHERE user_id = $1 AND conversation_id = $2
          ORDER BY timestamp DESC, message_id DESC
          LIMIT $3 OFFSET $4
        `, [userId, conversationId, limit, offset]);

        const messages = result.rows.map(row => ({
          id: row.id,
          type: row.type,
          content: row.content,
          suggestions: row.suggestions,
          context: row.context,
          timestamp: new Date(row.timestamp)
        })).reverse(); // Reverse to get chronological order

        console.log(`✅ Retrieved ${messages.length} messages from database`);
        return messages;
      } catch (error) {
        console.error('❌ Failed to retrieve messages from database:', error.message);
        this.dbAvailable = false;
      }
    }

    // Fallback to memory storage
    return this.getHistoryFromMemory(userId, conversationId, limit);
  }

  /**
   * Clear conversation history
   */
  async clearHistory(userId, conversationId) {
    const dbAvailable = await this.checkDatabaseAvailability();
    
    if (dbAvailable) {
      try {
        await query(`
          DELETE FROM ai_conversations 
          WHERE user_id = $1 AND conversation_id = $2
        `, [userId, conversationId]);

        await query(`
          DELETE FROM ai_conversation_metadata 
          WHERE user_id = $1 AND conversation_id = $2
        `, [userId, conversationId]);

        console.log(`✅ Cleared conversation history from database for user ${userId}`);
        return true;
      } catch (error) {
        console.error('❌ Failed to clear conversation from database:', error.message);
        this.dbAvailable = false;
      }
    }

    // Fallback to memory storage
    return this.clearHistoryFromMemory(userId, conversationId);
  }

  /**
   * Get conversation list for user
   */
  async getConversations(userId, limit = 20) {
    const dbAvailable = await this.checkDatabaseAvailability();
    
    if (dbAvailable) {
      try {
        const result = await query(`
          SELECT 
            conversation_id,
            title,
            summary,
            total_messages,
            last_activity,
            created_at
          FROM ai_conversation_metadata 
          WHERE user_id = $1
          ORDER BY last_activity DESC
          LIMIT $2
        `, [userId, limit]);

        return result.rows.map(row => ({
          conversationId: row.conversation_id,
          title: row.title || 'Untitled Conversation',
          summary: row.summary,
          totalMessages: row.total_messages,
          lastActivity: new Date(row.last_activity),
          createdAt: new Date(row.created_at)
        }));
      } catch (error) {
        console.error('❌ Failed to get conversations from database:', error.message);
        this.dbAvailable = false;
      }
    }

    // Return empty array for memory storage (not implementing conversation list for memory)
    return [];
  }

  /**
   * Memory storage fallback methods
   */
  addMessageToMemory(userId, conversationId, message) {
    const key = `${userId}:${conversationId}`;
    if (!this.memoryStore.has(key)) {
      this.memoryStore.set(key, []);
    }
    
    const conversation = this.memoryStore.get(key);
    conversation.push({
      ...message,
      timestamp: message.timestamp || new Date()
    });

    // Keep only last 100 messages in memory
    if (conversation.length > 100) {
      conversation.splice(0, conversation.length - 100);
    }

    this.memoryStore.set(key, conversation);
    console.log(`✅ Message stored in memory for user ${userId}`);
    return true;
  }

  getHistoryFromMemory(userId, conversationId, limit) {
    const key = `${userId}:${conversationId}`;
    const conversation = this.memoryStore.get(key) || [];
    return conversation.slice(-limit);
  }

  clearHistoryFromMemory(userId, conversationId) {
    const key = `${userId}:${conversationId}`;
    this.memoryStore.delete(key);
    console.log(`✅ Cleared conversation history from memory for user ${userId}`);
    return true;
  }

  /**
   * Get storage statistics
   */
  getStorageStats() {
    return {
      databaseAvailable: this.dbAvailable,
      lastDatabaseCheck: new Date(this.lastDbCheck),
      memoryConversations: this.memoryStore.size,
      storageMode: this.dbAvailable ? 'database' : 'memory'
    };
  }
}

// Export singleton instance
module.exports = new ConversationStore();