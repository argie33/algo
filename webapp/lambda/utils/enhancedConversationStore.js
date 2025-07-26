/**
 * Enhanced Conversation Store - Production-ready conversation management
 * 
 * Provides advanced conversation management with:
 * - Multi-conversation support
 * - Conversation analytics and insights
 * - Smart conversation organization
 * - Performance optimization
 * - Data integrity and backup
 */

const { query } = require('./database');

class EnhancedConversationStore {
  constructor() {
    this.initialized = false;
    this.cache = new Map(); // Cache for frequently accessed conversations
    this.analytics = {
      totalConversations: 0,
      totalMessages: 0,
      avgMessagesPerConversation: 0,
      userEngagement: new Map()
    };
    
    // Configuration
    this.config = {
      maxConversationsPerUser: 100,
      maxMessagesPerConversation: 1000,
      cacheSize: 500,
      cacheTTL: 30 * 60 * 1000, // 30 minutes
      analyticsUpdateInterval: 60000 // 1 minute
    };
  }

  /**
   * Initialize enhanced conversation storage
   */
  async initializeEnhancedTables() {
    try {
      console.log('🗄️ Initializing enhanced conversation storage...');

      // Create enhanced conversations table
      await query(`
        CREATE TABLE IF NOT EXISTS ai_conversations_enhanced (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          conversation_id VARCHAR(255) NOT NULL,
          message_id VARCHAR(255) NOT NULL,
          message_type VARCHAR(50) NOT NULL CHECK (message_type IN ('user', 'assistant', 'system')),
          content TEXT NOT NULL,
          metadata JSONB DEFAULT '{}',
          suggestions TEXT[] DEFAULT ARRAY[]::TEXT[],
          context JSONB DEFAULT '{}',
          timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          
          -- Enhanced fields
          parent_message_id VARCHAR(255),
          thread_id VARCHAR(255),
          importance_score INTEGER DEFAULT 5 CHECK (importance_score BETWEEN 1 AND 10),
          sentiment_score DECIMAL(3,2) DEFAULT 0.0 CHECK (sentiment_score BETWEEN -1.0 AND 1.0),
          topic_tags TEXT[] DEFAULT ARRAY[]::TEXT[],
          
          UNIQUE(user_id, conversation_id, message_id),
          INDEX(user_id, conversation_id, timestamp),
          INDEX(user_id, timestamp),
          INDEX(conversation_id, timestamp),
          INDEX(topic_tags) USING GIN,
          INDEX(metadata) USING GIN
        )
      `);

      // Create conversation metadata table
      await query(`
        CREATE TABLE IF NOT EXISTS ai_conversation_metadata (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          conversation_id VARCHAR(255) NOT NULL,
          
          -- Conversation info
          title VARCHAR(500),
          description TEXT,
          total_messages INTEGER DEFAULT 0,
          last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          
          -- Analytics
          engagement_score DECIMAL(5,2) DEFAULT 0.0,
          avg_response_time INTEGER DEFAULT 0,
          user_satisfaction DECIMAL(3,2) DEFAULT 0.0,
          
          -- Organization
          folder VARCHAR(255) DEFAULT 'general',
          tags TEXT[] DEFAULT ARRAY[]::TEXT[],
          pinned BOOLEAN DEFAULT FALSE,
          archived BOOLEAN DEFAULT FALSE,
          
          -- Settings
          settings JSONB DEFAULT '{}',
          
          UNIQUE(user_id, conversation_id),
          INDEX(user_id, last_activity),
          INDEX(user_id, pinned, archived),
          INDEX(tags) USING GIN
        )
      `);

      // Create user conversation preferences
      await query(`
        CREATE TABLE IF NOT EXISTS ai_user_conversation_preferences (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL UNIQUE,
          
          -- Display preferences
          conversation_ordering VARCHAR(50) DEFAULT 'last_activity',
          messages_per_page INTEGER DEFAULT 50,
          show_timestamps BOOLEAN DEFAULT TRUE,
          compact_view BOOLEAN DEFAULT FALSE,
          
          -- AI behavior preferences
          response_style VARCHAR(50) DEFAULT 'balanced',
          auto_suggest BOOLEAN DEFAULT TRUE,
          context_depth INTEGER DEFAULT 10,
          preferred_model VARCHAR(100) DEFAULT 'claude-3-haiku',
          
          -- Organization preferences
          auto_organize BOOLEAN DEFAULT TRUE,
          auto_title BOOLEAN DEFAULT TRUE,
          folder_structure JSONB DEFAULT '{"folders": ["general", "portfolio", "research", "planning"]}',
          
          -- Privacy settings
          data_retention_days INTEGER DEFAULT 365,
          analytics_enabled BOOLEAN DEFAULT TRUE,
          
          created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
          updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
      `);

      // Create conversation analytics table
      await query(`
        CREATE TABLE IF NOT EXISTS ai_conversation_analytics (
          id SERIAL PRIMARY KEY,
          user_id VARCHAR(255) NOT NULL,
          conversation_id VARCHAR(255),
          date DATE NOT NULL DEFAULT CURRENT_DATE,
          
          -- Daily metrics
          messages_sent INTEGER DEFAULT 0,
          ai_responses INTEGER DEFAULT 0,
          avg_response_time INTEGER DEFAULT 0,
          session_duration INTEGER DEFAULT 0,
          
          -- Engagement metrics
          suggestions_used INTEGER DEFAULT 0,
          follow_up_questions INTEGER DEFAULT 0,
          user_rating_sum INTEGER DEFAULT 0,
          user_rating_count INTEGER DEFAULT 0,
          
          -- Topic analysis
          topics JSONB DEFAULT '{}',
          sentiment_trend DECIMAL(3,2) DEFAULT 0.0,
          
          UNIQUE(user_id, conversation_id, date),
          INDEX(user_id, date),
          INDEX(date)
        )
      `);

      // Create update triggers
      await query(`
        CREATE OR REPLACE FUNCTION update_conversation_metadata()
        RETURNS TRIGGER AS $$
        BEGIN
          -- Update conversation metadata when messages are added
          INSERT INTO ai_conversation_metadata (user_id, conversation_id, total_messages, last_activity)
          VALUES (NEW.user_id, NEW.conversation_id, 1, NEW.timestamp)
          ON CONFLICT (user_id, conversation_id)
          DO UPDATE SET
            total_messages = ai_conversation_metadata.total_messages + 1,
            last_activity = NEW.timestamp;
          
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
      `);

      await query(`
        DROP TRIGGER IF EXISTS update_conversation_metadata_trigger ON ai_conversations_enhanced;
        CREATE TRIGGER update_conversation_metadata_trigger
          AFTER INSERT ON ai_conversations_enhanced
          FOR EACH ROW EXECUTE FUNCTION update_conversation_metadata();
      `);

      this.initialized = true;
      console.log('✅ Enhanced conversation storage initialized successfully');

      // Start analytics updater
      this.startAnalyticsUpdater();

    } catch (error) {
      console.error('❌ Failed to initialize enhanced conversation storage:', error);
      throw error;
    }
  }

  /**
   * Add enhanced message to conversation
   */
  async addEnhancedMessage(userId, conversationId, message, options = {}) {
    try {
      const {
        parentMessageId = null,
        threadId = null,
        importanceScore = 5,
        topicTags = [],
        autoAnalyze = true
      } = options;

      // Generate message ID if not provided
      const messageId = message.id || `msg_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;

      // Analyze message for sentiment and topics if enabled
      let sentimentScore = 0;
      let analyzedTags = topicTags;

      if (autoAnalyze && message.content) {
        const analysis = await this.analyzeMessage(message.content, message.type);
        sentimentScore = analysis.sentiment;
        analyzedTags = [...topicTags, ...analysis.topics];
      }

      // Insert enhanced message
      await query(`
        INSERT INTO ai_conversations_enhanced (
          user_id, conversation_id, message_id, message_type, content,
          metadata, suggestions, context, timestamp,
          parent_message_id, thread_id, importance_score, sentiment_score, topic_tags
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
      `, [
        userId,
        conversationId,
        messageId,
        message.type,
        message.content,
        JSON.stringify(message.metadata || {}),
        message.suggestions || [],
        JSON.stringify(message.context || {}),
        message.timestamp || new Date(),
        parentMessageId,
        threadId,
        importanceScore,
        sentimentScore,
        analyzedTags
      ]);

      // Update cache
      this.updateCache(userId, conversationId);

      // Update analytics
      await this.updateDailyAnalytics(userId, conversationId, message.type);

      console.log(`✅ Enhanced message added: ${messageId} to conversation ${conversationId}`);

      return {
        messageId,
        sentimentScore,
        topicTags: analyzedTags,
        success: true
      };

    } catch (error) {
      console.error('❌ Error adding enhanced message:', error);
      throw error;
    }
  }

  /**
   * Get enhanced conversation history with analytics
   */
  async getEnhancedHistory(userId, conversationId, options = {}) {
    try {
      const {
        limit = 50,
        offset = 0,
        includeAnalytics = true,
        includeThreads = false,
        topicFilter = null,
        sentimentFilter = null
      } = options;

      // Check cache first
      const cacheKey = `${userId}:${conversationId}:${limit}:${offset}`;
      const cached = this.cache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < this.config.cacheTTL) {
        return cached.data;
      }

      // Build query with filters
      let whereClause = 'WHERE user_id = $1 AND conversation_id = $2';
      let params = [userId, conversationId];
      let paramIndex = 3;

      if (topicFilter) {
        whereClause += ` AND $${paramIndex} = ANY(topic_tags)`;
        params.push(topicFilter);
        paramIndex++;
      }

      if (sentimentFilter) {
        const { min = -1, max = 1 } = sentimentFilter;
        whereClause += ` AND sentiment_score BETWEEN $${paramIndex} AND $${paramIndex + 1}`;
        params.push(min, max);
        paramIndex += 2;
      }

      // Get messages
      const messagesResult = await query(`
        SELECT 
          message_id, message_type, content, metadata, suggestions, context,
          timestamp, parent_message_id, thread_id, importance_score,
          sentiment_score, topic_tags
        FROM ai_conversations_enhanced
        ${whereClause}
        ORDER BY timestamp ASC
        LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
      `, [...params, limit, offset]);

      // Get conversation metadata if including analytics
      let conversationMeta = null;
      if (includeAnalytics) {
        const metaResult = await query(`
          SELECT title, description, total_messages, engagement_score,
                 avg_response_time, user_satisfaction, folder, tags, pinned
          FROM ai_conversation_metadata
          WHERE user_id = $1 AND conversation_id = $2
        `, [userId, conversationId]);

        conversationMeta = metaResult.rows[0] || null;
      }

      // Process messages
      const messages = messagesResult.rows.map(row => ({
        id: row.message_id,
        type: row.message_type,
        content: row.content,
        metadata: row.metadata,
        suggestions: row.suggestions,
        context: row.context,
        timestamp: row.timestamp,
        parentMessageId: row.parent_message_id,
        threadId: row.thread_id,
        importanceScore: row.importance_score,
        sentimentScore: row.sentiment_score,
        topicTags: row.topic_tags
      }));

      const result = {
        messages,
        conversationMeta,
        totalMessages: conversationMeta?.total_messages || messages.length,
        analytics: includeAnalytics ? await this.getConversationAnalytics(userId, conversationId) : null
      };

      // Cache result
      this.cache.set(cacheKey, {
        data: result,
        timestamp: Date.now()
      });

      return result;

    } catch (error) {
      console.error('❌ Error getting enhanced history:', error);
      throw error;
    }
  }

  /**
   * Get all conversations for user with enhanced metadata
   */
  async getEnhancedConversations(userId, options = {}) {
    try {
      const {
        limit = 50,
        offset = 0,
        includeArchived = false,
        folder = null,
        sortBy = 'last_activity',
        sortOrder = 'DESC'
      } = options;

      let whereClause = 'WHERE user_id = $1';
      let params = [userId];
      let paramIndex = 2;

      if (!includeArchived) {
        whereClause += ' AND archived = FALSE';
      }

      if (folder) {
        whereClause += ` AND folder = $${paramIndex}`;
        params.push(folder);
        paramIndex++;
      }

      const conversationsResult = await query(`
        SELECT 
          conversation_id, title, description, total_messages, last_activity,
          engagement_score, avg_response_time, user_satisfaction,
          folder, tags, pinned, archived, created_at
        FROM ai_conversation_metadata
        ${whereClause}
        ORDER BY ${sortBy} ${sortOrder}
        LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
      `, [...params, limit, offset]);

      const conversations = conversationsResult.rows.map(row => ({
        conversationId: row.conversation_id,
        title: row.title,
        description: row.description,
        totalMessages: row.total_messages,
        lastActivity: row.last_activity,
        engagementScore: parseFloat(row.engagement_score || 0),
        avgResponseTime: row.avg_response_time,
        userSatisfaction: parseFloat(row.user_satisfaction || 0),
        folder: row.folder,
        tags: row.tags,
        pinned: row.pinned,
        archived: row.archived,
        createdAt: row.created_at
      }));

      return conversations;

    } catch (error) {
      console.error('❌ Error getting enhanced conversations:', error);
      throw error;
    }
  }

  /**
   * Update conversation metadata
   */
  async updateConversationMetadata(userId, conversationId, updates) {
    try {
      const allowedFields = [
        'title', 'description', 'folder', 'tags', 'pinned', 'archived', 'settings'
      ];

      const setClause = [];
      const params = [userId, conversationId];
      let paramIndex = 3;

      for (const [field, value] of Object.entries(updates)) {
        if (allowedFields.includes(field)) {
          if (field === 'tags' && Array.isArray(value)) {
            setClause.push(`${field} = $${paramIndex}`);
            params.push(value);
          } else if (field === 'settings' && typeof value === 'object') {
            setClause.push(`${field} = $${paramIndex}`);
            params.push(JSON.stringify(value));
          } else {
            setClause.push(`${field} = $${paramIndex}`);
            params.push(value);
          }
          paramIndex++;
        }
      }

      if (setClause.length === 0) {
        throw new Error('No valid fields to update');
      }

      setClause.push('updated_at = NOW()');

      await query(`
        UPDATE ai_conversation_metadata
        SET ${setClause.join(', ')}
        WHERE user_id = $1 AND conversation_id = $2
      `, params);

      // Clear cache for this conversation
      this.clearCache(userId, conversationId);

      console.log(`✅ Updated conversation metadata for ${conversationId}`);

    } catch (error) {
      console.error('❌ Error updating conversation metadata:', error);
      throw error;
    }
  }

  /**
   * Smart conversation organization
   */
  async organizeConversations(userId, options = {}) {
    try {
      const {
        autoTitle = true,
        autoFolder = true,
        autoTags = true
      } = options;

      console.log(`🗂️ Organizing conversations for user ${userId}...`);

      // Get unorganized conversations
      const conversations = await query(`
        SELECT conversation_id, title, total_messages
        FROM ai_conversation_metadata
        WHERE user_id = $1 
        AND (title IS NULL OR title = '' OR folder = 'general')
        AND total_messages >= 3
        ORDER BY last_activity DESC
        LIMIT 20
      `, [userId]);

      let organized = 0;

      for (const conv of conversations.rows) {
        const updates = {};

        if (autoTitle && (!conv.title || conv.title === '')) {
          // Generate title from first few messages
          const titleResult = await this.generateConversationTitle(userId, conv.conversation_id);
          if (titleResult) {
            updates.title = titleResult;
          }
        }

        if (autoFolder || autoTags) {
          // Analyze conversation topics
          const topics = await this.analyzeConversationTopics(userId, conv.conversation_id);
          
          if (autoFolder) {
            updates.folder = this.suggestFolder(topics);
          }
          
          if (autoTags) {
            updates.tags = topics.slice(0, 5); // Top 5 topics as tags
          }
        }

        if (Object.keys(updates).length > 0) {
          await this.updateConversationMetadata(userId, conv.conversation_id, updates);
          organized++;
        }
      }

      console.log(`✅ Organized ${organized} conversations`);
      return { organized, total: conversations.rows.length };

    } catch (error) {
      console.error('❌ Error organizing conversations:', error);
      throw error;
    }
  }

  /**
   * Generate conversation title from content
   */
  async generateConversationTitle(userId, conversationId) {
    try {
      // Get first few messages
      const messages = await query(`
        SELECT content, message_type
        FROM ai_conversations_enhanced
        WHERE user_id = $1 AND conversation_id = $2
        AND message_type = 'user'
        ORDER BY timestamp ASC
        LIMIT 3
      `, [userId, conversationId]);

      if (messages.rows.length === 0) return null;

      // Extract keywords and create title
      const firstMessage = messages.rows[0].content;
      const words = firstMessage.split(' ').slice(0, 8).join(' ');
      
      // Clean and format title
      let title = words.length > 50 ? words.substring(0, 47) + '...' : words;
      title = title.charAt(0).toUpperCase() + title.slice(1);

      return title;

    } catch (error) {
      console.error('❌ Error generating conversation title:', error);
      return null;
    }
  }

  /**
   * Analyze conversation topics
   */
  async analyzeConversationTopics(userId, conversationId) {
    try {
      // Get all messages from conversation
      const messages = await query(`
        SELECT content, topic_tags
        FROM ai_conversations_enhanced
        WHERE user_id = $1 AND conversation_id = $2
        ORDER BY timestamp ASC
      `, [userId, conversationId]);

      const topicCounts = {};
      const financialKeywords = {
        'portfolio': ['portfolio', 'holdings', 'investments', 'positions'],
        'stocks': ['stock', 'stocks', 'equity', 'shares', 'ticker'],
        'market': ['market', 'markets', 'trading', 'volatility'],
        'analysis': ['analyze', 'analysis', 'research', 'evaluation'],
        'planning': ['plan', 'planning', 'strategy', 'goal', 'retirement'],
        'risk': ['risk', 'risks', 'volatility', 'diversification'],
        'performance': ['performance', 'returns', 'gains', 'losses']
      };

      // Analyze content for topics
      messages.rows.forEach(row => {
        const content = row.content.toLowerCase();
        
        // Check existing tags
        if (row.topic_tags && row.topic_tags.length > 0) {
          row.topic_tags.forEach(tag => {
            topicCounts[tag] = (topicCounts[tag] || 0) + 1;
          });
        }

        // Check for financial keywords
        Object.entries(financialKeywords).forEach(([topic, keywords]) => {
          keywords.forEach(keyword => {
            if (content.includes(keyword)) {
              topicCounts[topic] = (topicCounts[topic] || 0) + 1;
            }
          });
        });
      });

      // Return top topics
      return Object.entries(topicCounts)
        .sort(([,a], [,b]) => b - a)
        .slice(0, 10)
        .map(([topic]) => topic);

    } catch (error) {
      console.error('❌ Error analyzing conversation topics:', error);
      return [];
    }
  }

  /**
   * Suggest folder based on topics
   */
  suggestFolder(topics) {
    const folderMappings = {
      'portfolio': ['portfolio', 'holdings', 'positions'],
      'research': ['analysis', 'research', 'stocks', 'market'],
      'planning': ['planning', 'strategy', 'goal', 'retirement'],
      'trading': ['trading', 'market', 'volatility']
    };

    for (const [folder, keywords] of Object.entries(folderMappings)) {
      if (topics.some(topic => keywords.includes(topic))) {
        return folder;
      }
    }

    return 'general';
  }

  /**
   * Analyze message for sentiment and topics
   */
  async analyzeMessage(content, messageType) {
    try {
      // Simple sentiment analysis (production would use NLP service)
      const positiveWords = ['good', 'great', 'excellent', 'positive', 'up', 'gain', 'profit'];
      const negativeWords = ['bad', 'terrible', 'negative', 'down', 'loss', 'decline'];
      
      const words = content.toLowerCase().split(/\s+/);
      let sentimentScore = 0;
      
      words.forEach(word => {
        if (positiveWords.includes(word)) sentimentScore += 0.1;
        if (negativeWords.includes(word)) sentimentScore -= 0.1;
      });

      // Clamp between -1 and 1
      sentimentScore = Math.max(-1, Math.min(1, sentimentScore));

      // Extract topics (simplified keyword extraction)
      const topics = [];
      const topicKeywords = {
        'portfolio': /portfolio|holdings|investments/i,
        'stocks': /stock|equity|shares|ticker/i,
        'market': /market|trading|volatility/i,
        'analysis': /analyz|research|evaluat/i,
        'planning': /plan|strategy|goal/i
      };

      Object.entries(topicKeywords).forEach(([topic, regex]) => {
        if (regex.test(content)) {
          topics.push(topic);
        }
      });

      return {
        sentiment: sentimentScore,
        topics
      };

    } catch (error) {
      console.error('❌ Error analyzing message:', error);
      return { sentiment: 0, topics: [] };
    }
  }

  /**
   * Get conversation analytics
   */
  async getConversationAnalytics(userId, conversationId = null) {
    try {
      let whereClause = 'WHERE user_id = $1';
      let params = [userId];

      if (conversationId) {
        whereClause += ' AND conversation_id = $2';
        params.push(conversationId);
      }

      const analyticsResult = await query(`
        SELECT 
          DATE(date) as date,
          SUM(messages_sent) as messages_sent,
          SUM(ai_responses) as ai_responses,
          AVG(avg_response_time) as avg_response_time,
          SUM(session_duration) as session_duration,
          AVG(CASE WHEN user_rating_count > 0 THEN user_rating_sum::DECIMAL / user_rating_count ELSE 0 END) as avg_rating
        FROM ai_conversation_analytics
        ${whereClause}
        AND date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY DATE(date)
        ORDER BY date DESC
      `, params);

      return analyticsResult.rows;

    } catch (error) {
      console.error('❌ Error getting conversation analytics:', error);
      return [];
    }
  }

  /**
   * Update daily analytics
   */
  async updateDailyAnalytics(userId, conversationId, messageType) {
    try {
      const today = new Date().toISOString().split('T')[0];
      
      await query(`
        INSERT INTO ai_conversation_analytics 
        (user_id, conversation_id, date, messages_sent, ai_responses)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id, conversation_id, date)
        DO UPDATE SET
          messages_sent = ai_conversation_analytics.messages_sent + $4,
          ai_responses = ai_conversation_analytics.ai_responses + $5
      `, [
        userId,
        conversationId,
        today,
        messageType === 'user' ? 1 : 0,
        messageType === 'assistant' ? 1 : 0
      ]);

    } catch (error) {
      console.error('❌ Error updating daily analytics:', error);
    }
  }

  /**
   * Cache management
   */
  updateCache(userId, conversationId) {
    // Remove related cache entries
    for (const [key] of this.cache) {
      if (key.startsWith(`${userId}:${conversationId}:`)) {
        this.cache.delete(key);
      }
    }
  }

  clearCache(userId, conversationId = null) {
    if (conversationId) {
      this.updateCache(userId, conversationId);
    } else {
      // Clear all cache for user
      for (const [key] of this.cache) {
        if (key.startsWith(`${userId}:`)) {
          this.cache.delete(key);
        }
      }
    }
  }

  /**
   * Start analytics updater
   */
  startAnalyticsUpdater() {
    setInterval(async () => {
      try {
        await this.updateGlobalAnalytics();
      } catch (error) {
        console.error('❌ Analytics update error:', error);
      }
    }, this.config.analyticsUpdateInterval);
  }

  /**
   * Update global analytics
   */
  async updateGlobalAnalytics() {
    try {
      const stats = await query(`
        SELECT 
          COUNT(DISTINCT conversation_id) as total_conversations,
          COUNT(*) as total_messages,
          COUNT(DISTINCT user_id) as active_users
        FROM ai_conversations_enhanced
        WHERE timestamp >= NOW() - INTERVAL '30 days'
      `);

      if (stats.rows.length > 0) {
        const row = stats.rows[0];
        this.analytics.totalConversations = parseInt(row.total_conversations);
        this.analytics.totalMessages = parseInt(row.total_messages);
        this.analytics.avgMessagesPerConversation = 
          this.analytics.totalConversations > 0 ? 
          this.analytics.totalMessages / this.analytics.totalConversations : 0;
      }

    } catch (error) {
      console.error('❌ Error updating global analytics:', error);
    }
  }

  /**
   * Get enhanced storage stats
   */
  getEnhancedStats() {
    return {
      ...this.analytics,
      cacheSize: this.cache.size,
      maxCacheSize: this.config.cacheSize,
      initialized: this.initialized,
      config: this.config
    };
  }

  /**
   * Clean up old conversations
   */
  async cleanupOldConversations(retentionDays = 365) {
    try {
      const cutoffDate = new Date();
      cutoffDate.setDate(cutoffDate.getDate() - retentionDays);

      // Archive old conversations instead of deleting
      const archivedCount = await query(`
        UPDATE ai_conversation_metadata
        SET archived = TRUE
        WHERE last_activity < $1 AND archived = FALSE
      `, [cutoffDate]);

      console.log(`📦 Archived ${archivedCount.rowCount} old conversations`);

      return archivedCount.rowCount;

    } catch (error) {
      console.error('❌ Error cleaning up conversations:', error);
      return 0;
    }
  }
}

// Export singleton instance
module.exports = new EnhancedConversationStore();