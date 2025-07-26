/**
 * AI Streaming Service - WebSocket-based streaming responses
 * 
 * Provides real-time streaming of AI responses for better user experience
 */

const bedrockAIService = require('./bedrockAIService');
const conversationStore = require('./conversationStore');

class AIStreamingService {
  constructor() {
    this.activeStreams = new Map();
    this.io = null; // Will be set when Socket.IO is initialized
  }

  /**
   * Initialize with Socket.IO instance
   */
  initialize(socketIO) {
    this.io = socketIO;
    console.log('✅ AI Streaming service initialized with WebSocket support');
  }

  /**
   * Stream AI response in real-time
   */
  async streamResponse(userId, socketId, message, context = {}) {
    const streamId = `${userId}_${Date.now()}`;
    const startTime = Date.now();
    
    console.log(`🔄 Starting AI stream ${streamId} for user ${userId}`);
    
    this.activeStreams.set(streamId, {
      userId,
      socketId,
      startTime,
      message,
      context
    });

    try {
      if (!this.io) {
        throw new Error('WebSocket not initialized - falling back to regular response');
      }

      // Emit stream start event
      this.io.to(socketId).emit('ai_stream_start', {
        streamId,
        message,
        timestamp: startTime
      });

      // Generate response with streaming callback
      const response = await bedrockAIService.generateResponse(message, context, {
        onChunk: (chunk, chunkIndex) => {
          // Stream each chunk to frontend
          this.io.to(socketId).emit('ai_stream_chunk', {
            streamId,
            chunk,
            chunkIndex,
            timestamp: Date.now()
          });
        },
        onProgress: (progress) => {
          // Stream progress updates
          this.io.to(socketId).emit('ai_stream_progress', {
            streamId,
            progress, // 0-100
            timestamp: Date.now()
          });
        }
      });

      const duration = Date.now() - startTime;
      
      // Emit stream completion
      this.io.to(socketId).emit('ai_stream_complete', {
        streamId,
        response,
        duration,
        timestamp: Date.now()
      });

      console.log(`✅ AI stream ${streamId} completed in ${duration}ms`);
      return response;

    } catch (error) {
      console.error(`❌ AI stream ${streamId} failed:`, error.message);
      
      if (this.io) {
        this.io.to(socketId).emit('ai_stream_error', {
          streamId,
          error: {
            message: error.message,
            code: error.code || 'STREAM_ERROR',
            type: error.name || 'StreamingError'
          },
          timestamp: Date.now()
        });
      }

      throw error;
    } finally {
      this.activeStreams.delete(streamId);
    }
  }

  /**
   * Stop active stream
   */
  stopStream(streamId) {
    const stream = this.activeStreams.get(streamId);
    if (stream && this.io) {
      this.io.to(stream.socketId).emit('ai_stream_stopped', {
        streamId,
        timestamp: Date.now()
      });
      this.activeStreams.delete(streamId);
      console.log(`🛑 Stopped AI stream ${streamId}`);
      return true;
    }
    return false;
  }

  /**
   * Get active stream statistics
   */
  getStreamStats() {
    const now = Date.now(); 
    const activeStreams = Array.from(this.activeStreams.values()).map(stream => ({
      streamId: `${stream.userId}_${stream.startTime}`,
      userId: stream.userId,
      duration: now - stream.startTime,
      message: stream.message.substring(0, 50) + '...'
    }));

    return {
      activeStreamCount: this.activeStreams.size,
      activeStreams,
      webSocketReady: !!this.io
    };
  }

  /**
   * Handle WebSocket connection for AI streaming
   */
  handleConnection(socket) {
    console.log(`🔌 WebSocket connected for AI streaming: ${socket.id}`);

    // Join user to their personal room for targeted messaging
    socket.on('join_ai_room', (data) => {
      const { userId } = data;
      if (userId) {
        socket.join(`user_${userId}`);
        socket.emit('ai_room_joined', { userId, socketId: socket.id });
        console.log(`👤 User ${userId} joined AI room with socket ${socket.id}`);
      }
    });

    // Handle stream request
    socket.on('request_ai_stream', async (data) => {
      const { userId, message, context } = data;
      if (!userId || !message) {
        socket.emit('ai_stream_error', {
          error: { message: 'Missing userId or message', code: 'INVALID_REQUEST' }
        });
        return;
      }

      try {
        await this.streamResponse(userId, socket.id, message, context);
      } catch (error) {
        console.error('WebSocket stream request failed:', error);
      }
    });

    // Handle stream stop request
    socket.on('stop_ai_stream', (data) => {
      const { streamId } = data;
      if (streamId) {
        this.stopStream(streamId);
      }
    });

    socket.on('disconnect', () => {
      console.log(`🔌 WebSocket disconnected: ${socket.id}`);
      // Clean up any active streams for this socket
      for (const [streamId, stream] of this.activeStreams.entries()) {
        if (stream.socketId === socket.id) {
          this.activeStreams.delete(streamId);
          console.log(`🧹 Cleaned up abandoned stream: ${streamId}`);
        }
      }
    });
  }
}

// Export singleton instance
module.exports = new AIStreamingService();