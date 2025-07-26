# Complete AI Agent Design Specification

## Overview

Design for a production-ready ChatGPT-like AI agent built on existing foundation, targeting enterprise-grade financial advisory capabilities with real-time streaming, persistent conversations, and intelligent context awareness.

## System Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend Layer                          │
├─────────────────────────────────────────────────────────────────┤
│ React App (AIAssistant.jsx)                                    │
│ ├── Chat Interface                                             │
│ ├── Conversation History                                       │ 
│ ├── Real-time Streaming                                        │
│ ├── Context Management                                         │
│ └── Analytics Dashboard                                        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway & Load Balancer                │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Backend Services                         │
├─────────────────────────────────────────────────────────────────┤
│ Lambda Functions                                               │
│ ├── AI Assistant Routes (/api/ai/*)                           │
│ ├── WebSocket Handler                                          │
│ ├── Conversation Manager                                       │
│ ├── Context Aggregator                                         │
│ └── Analytics Processor                                        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                        ┌───────────┼───────────┐
                        ▼           ▼           ▼
┌─────────────────┐ ┌──────────────┐ ┌─────────────────┐
│   AWS Bedrock   │ │  PostgreSQL  │ │   Redis Cache   │
│   Claude 3      │ │  Database    │ │   Session Store │
│   Haiku/Sonnet  │ │              │ │                 │
└─────────────────┘ └──────────────┘ └─────────────────┘
```

### Component Architecture

```
AI Agent Core Components:

┌─────────────────────────────────────────┐
│            AI Orchestrator              │
├─────────────────────────────────────────┤
│ ├── Conversation Manager                │
│ ├── Context Aggregator                  │
│ ├── Response Generator                   │
│ ├── Streaming Controller                │
│ └── Error Recovery System               │
└─────────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
┌──────────────┐ ┌──────────┐ ┌──────────────┐
│   Bedrock    │ │ Database │ │    Cache     │
│   Service    │ │ Service  │ │   Service    │
└──────────────┘ └──────────┘ └──────────────┘
```

## Core Components Design

### 1. Enhanced Chat Interface

**File: `/webapp/frontend/src/components/EnhancedAIChat.jsx`**

```jsx
// Key Features:
- Real-time message streaming with typing indicators
- Conversation threading and branching
- Rich message formatting (markdown, code blocks, tables)
- Context-aware suggestions
- Message actions (copy, edit, regenerate)
- Conversation search and filtering
- Export conversations
```

**Design Specifications:**
- **Streaming**: WebSocket connection for real-time responses
- **State Management**: React Query for caching and synchronization
- **UI Components**: Material-UI with custom chat components
- **Accessibility**: ARIA labels, keyboard navigation, screen reader support
- **Performance**: Virtual scrolling for large conversations

### 2. Conversation Management System

**File: `/webapp/lambda/services/ConversationManager.js`**

```javascript
class ConversationManager {
  // Enhanced conversation handling
  async createConversation(userId, title, metadata)
  async updateConversationContext(conversationId, context)
  async getConversationSummary(conversationId)
  async mergeConversations(conversationIds)
  async forkConversation(conversationId, messageId)
  async searchConversations(userId, query, filters)
  async exportConversation(conversationId, format)
}
```

**Features:**
- **Threading**: Support for conversation branching
- **Context Tracking**: Maintain conversation context across sessions
- **Search**: Full-text search across conversations
- **Analytics**: Track conversation metrics and patterns
- **Export**: Multiple formats (JSON, Markdown, PDF)

### 3. Streaming Response System

**File: `/webapp/lambda/services/StreamingService.js`**

```javascript
class StreamingService {
  async streamResponse(userId, socketId, message, context)
  async handleWebSocketConnection(socket)
  async broadcastToUser(userId, data)
  async handleStreamingError(error, context)
}
```

**WebSocket Events:**
```javascript
// Client → Server
'ai_message_start'    // Start new message
'ai_message_stream'   // Continue streaming
'ai_message_complete' // Message complete
'ai_typing_start'     // User typing
'ai_typing_stop'      // User stopped typing

// Server → Client  
'ai_response_chunk'   // Partial response
'ai_response_complete'// Complete response
'ai_error'           // Error occurred
'ai_suggestions'     // Follow-up suggestions
```

### 4. Context Intelligence Engine

**File: `/webapp/lambda/services/ContextEngine.js`**

```javascript
class ContextEngine {
  async aggregateUserContext(userId)
  async extractMessageContext(message, history)
  async updateConversationContext(conversationId, newContext)
  async getRelevantMarketData(context)
  async getPortfolioInsights(userId, context)
  async generateContextualSuggestions(context)
}
```

**Context Types:**
- **User Profile**: Investment preferences, risk tolerance, goals
- **Portfolio State**: Current holdings, performance, allocation
- **Market Context**: Real-time market data, news, trends
- **Conversation History**: Recent messages, topics, decisions
- **Session Context**: Current conversation flow, active topics

### 5. Enhanced Bedrock Integration

**File: `/webapp/lambda/services/EnhancedBedrockService.js`**

```javascript
class EnhancedBedrockService extends BedrockAIService {
  // Enhanced capabilities
  async generateStreamingResponse(message, context)
  async generateWithTools(message, availableTools)
  async generateWithMemory(message, longTermMemory)
  async evaluateResponseQuality(response, context)
  async adaptModelParameters(conversationMetrics)
}
```

**New Features:**
- **Streaming Responses**: Token-by-token streaming
- **Tool Integration**: Calculator, chart generator, data analyzer
- **Memory Management**: Long-term conversation memory
- **Quality Control**: Response validation and improvement
- **Adaptive Parameters**: Dynamic temperature/top-p adjustment

## Database Schema Enhancement

### Enhanced Conversation Tables

```sql
-- Enhanced conversation metadata
CREATE TABLE ai_conversation_metadata (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  conversation_id VARCHAR(255) NOT NULL,
  title VARCHAR(500),
  summary TEXT,
  tags TEXT[], -- Conversation tags
  context JSONB, -- Persistent context
  total_messages INTEGER DEFAULT 0,
  total_tokens INTEGER DEFAULT 0,
  last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  -- Performance indexes
  INDEX(user_id, last_activity),
  INDEX(user_id, tags),
  UNIQUE(user_id, conversation_id)
);

-- Message threading support
CREATE TABLE ai_conversation_threads (
  id SERIAL PRIMARY KEY,
  conversation_id VARCHAR(255) NOT NULL,
  parent_message_id BIGINT,
  thread_id VARCHAR(255) NOT NULL,
  branch_point BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  INDEX(conversation_id, thread_id),
  INDEX(parent_message_id)
);

-- User AI preferences
CREATE TABLE ai_user_preferences (
  id SERIAL PRIMARY KEY,
  user_id VARCHAR(255) UNIQUE NOT NULL,
  preferred_model VARCHAR(100) DEFAULT 'claude-3-haiku',
  response_style VARCHAR(50) DEFAULT 'balanced', -- concise, detailed, balanced
  expertise_level VARCHAR(50) DEFAULT 'intermediate', -- beginner, intermediate, expert
  topics_of_interest TEXT[],
  conversation_settings JSONB,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  INDEX(user_id)
);

-- Conversation analytics
CREATE TABLE ai_conversation_analytics (
  id SERIAL PRIMARY KEY,
  conversation_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  session_duration INTEGER, -- seconds
  message_count INTEGER,
  token_count INTEGER,
  topics TEXT[],
  sentiment_score DECIMAL(3,2),
  satisfaction_score INTEGER, -- 1-5 rating
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  
  INDEX(user_id, created_at),
  INDEX(conversation_id)
);
```

## API Design

### REST Endpoints

```javascript
// Enhanced AI Assistant API
GET    /api/ai/config                    // Get AI configuration
PUT    /api/ai/preferences               // Update user preferences
GET    /api/ai/conversations             // List conversations
POST   /api/ai/conversations             // Create conversation
GET    /api/ai/conversations/:id         // Get conversation
PUT    /api/ai/conversations/:id         // Update conversation
DELETE /api/ai/conversations/:id         // Delete conversation
POST   /api/ai/conversations/:id/fork    // Fork conversation
GET    /api/ai/conversations/:id/export  // Export conversation

POST   /api/ai/chat                      // Send message (non-streaming)
POST   /api/ai/chat/stream              // Send message (streaming)
POST   /api/ai/chat/regenerate          // Regenerate last response
POST   /api/ai/chat/edit                // Edit and resubmit message

GET    /api/ai/suggestions              // Get contextual suggestions
GET    /api/ai/context                  // Get current context
POST   /api/ai/context/refresh          // Refresh context data

GET    /api/ai/analytics                // Get conversation analytics
GET    /api/ai/health                   // Service health check
```

### WebSocket Protocol

```javascript
// Connection management
ws://api.domain.com/ws/ai/{userId}

// Message protocol
{
  "type": "ai_message",
  "conversationId": "conv_123",
  "messageId": "msg_456", 
  "content": "What's my portfolio performance?",
  "context": { /* context data */ },
  "timestamp": "2024-01-20T10:30:00Z"
}

// Response protocol  
{
  "type": "ai_response_chunk",
  "conversationId": "conv_123",
  "messageId": "msg_457",
  "chunk": "Your portfolio has performed...",
  "isComplete": false,
  "suggestions": ["Tell me more", "Show charts"],
  "timestamp": "2024-01-20T10:30:02Z"
}
```

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1-2)

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"id": "design-1", "content": "Design complete AI agent architecture", "status": "completed", "priority": "high"}, {"id": "design-2", "content": "Design streaming chat interface", "status": "completed", "priority": "high"}, {"id": "design-3", "content": "Design AWS infrastructure setup", "status": "in_progress", "priority": "high"}, {"id": "phase1-1", "content": "Set up AWS Bedrock IAM permissions and model access", "status": "pending", "priority": "high"}, {"id": "phase1-2", "content": "Implement enhanced database schema", "status": "pending", "priority": "high"}, {"id": "phase1-3", "content": "Create WebSocket infrastructure", "status": "pending", "priority": "high"}, {"id": "phase1-4", "content": "Build streaming response system", "status": "pending", "priority": "high"}]