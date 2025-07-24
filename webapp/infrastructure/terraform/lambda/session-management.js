/**
 * Enhanced Session Management Lambda Function
 * Provides server-side session store with Redis backend
 */

const AWS = require('aws-sdk');
const Redis = require('ioredis');
const crypto = require('crypto');

// Initialize AWS services
const secretsManager = new AWS.SecretsManager();
const cognitoIdp = new AWS.CognitoIdentityServiceProvider();

// Global variables
let redis;
let secrets;

/**
 * Initialize Redis connection
 */
async function getRedisClient() {
  if (!redis) {
    try {
      // Get secrets if not already loaded
      if (!secrets) {
        const secretResponse = await secretsManager.getSecretValue({
          SecretId: process.env.SESSION_SECRETS_ARN
        }).promise();
        secrets = JSON.parse(secretResponse.SecretString);
      }

      // Initialize Redis with TLS
      redis = new Redis({
        host: process.env.REDIS_ENDPOINT,
        port: 6379,
        tls: true,
        retryDelayOnFailover: 100,
        maxRetriesPerRequest: 3,
        connectTimeout: 10000,
        commandTimeout: 5000,
        keyPrefix: `${secrets.project_name}:${secrets.environment}:`
      });

      redis.on('error', (err) => {
        console.error('Redis connection error:', err);
      });

      redis.on('connect', () => {
        console.log('Connected to Redis successfully');
      });

      // Test connection
      await redis.ping();
      console.log('Redis connection established');

    } catch (error) {
      console.error('Failed to initialize Redis:', error);
      throw error;
    }
  }
  return redis;
}

/**
 * Main Lambda handler
 */
exports.handler = async (event) => {
  console.log('Session management request:', JSON.stringify(event, null, 2));

  const { httpMethod, pathParameters, body, headers, requestContext } = event;
  const path = pathParameters?.proxy || '';

  // CORS headers
  const corsHeaders = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token',
    'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS',
    'Content-Type': 'application/json'
  };

  // Handle CORS preflight
  if (httpMethod === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: corsHeaders,
      body: ''
    };
  }

  try {
    const redisClient = await getRedisClient();
    let response;

    switch (httpMethod) {
      case 'POST':
        if (path === 'create') {
          response = await createSession(redisClient, JSON.parse(body || '{}'));
        } else if (path === 'validate') {
          response = await validateSession(redisClient, JSON.parse(body || '{}'));
        } else {
          response = { statusCode: 404, body: JSON.stringify({ error: 'Endpoint not found' }) };
        }
        break;

      case 'PUT':
        if (path === 'update') {
          response = await updateSession(redisClient, JSON.parse(body || '{}'));
        } else if (path === 'activity') {
          response = await updateActivity(redisClient, JSON.parse(body || '{}'));
        } else {
          response = { statusCode: 404, body: JSON.stringify({ error: 'Endpoint not found' }) };
        }
        break;

      case 'DELETE':
        if (path === 'revoke') {
          response = await revokeSession(redisClient, JSON.parse(body || '{}'));
        } else if (path === 'cleanup') {
          response = await cleanupExpiredSessions(redisClient, JSON.parse(body || '{}'));
        } else {
          response = { statusCode: 404, body: JSON.stringify({ error: 'Endpoint not found' }) };
        }
        break;

      case 'GET':
        if (path === 'status') {
          response = await getSessionStatus(redisClient, event.queryStringParameters || {});
        } else if (path === 'list') {
          response = await listUserSessions(redisClient, event.queryStringParameters || {});
        } else {
          response = { statusCode: 404, body: JSON.stringify({ error: 'Endpoint not found' }) };
        }
        break;

      default:
        response = {
          statusCode: 405,
          body: JSON.stringify({ error: 'Method not allowed' })
        };
    }

    return {
      ...response,
      headers: { ...corsHeaders, ...response.headers }
    };

  } catch (error) {
    console.error('Session management error:', error);
    return {
      statusCode: 500,
      headers: corsHeaders,
      body: JSON.stringify({
        error: 'Internal server error',
        message: error.message
      })
    };
  }
};

/**
 * Create new session
 */
async function createSession(redis, { userId, sessionId, deviceFingerprint, metadata }) {
  try {
    if (!userId || !sessionId) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'userId and sessionId are required' })
      };
    }

    const sessionKey = `session:${userId}:${sessionId}`;
    const userSessionsKey = `user:${userId}:sessions`;
    const deviceKey = `device:${userId}:${deviceFingerprint}`;

    const now = Date.now();
    const sessionData = {
      userId,
      sessionId,
      deviceFingerprint,
      ...metadata,
      createdAt: now,
      lastActivity: now,
      expiresAt: now + (24 * 60 * 60 * 1000), // 24 hours
      version: 1
    };

    // Store session data with TTL
    await redis.setex(sessionKey, 86400, JSON.stringify(sessionData));

    // Add session to user's session list
    await redis.sadd(userSessionsKey, sessionId);
    await redis.expire(userSessionsKey, 86400);

    // Track device for this user
    await redis.setex(deviceKey, 86400, JSON.stringify({
      sessionId,
      lastSeen: now,
      fingerprint: deviceFingerprint
    }));

    // Enforce concurrent session limit
    const sessions = await redis.smembers(userSessionsKey);
    const MAX_SESSIONS = 5;

    if (sessions.length > MAX_SESSIONS) {
      // Remove oldest sessions
      const sessionDetails = await Promise.all(
        sessions.map(async (sid) => {
          const data = await redis.get(`session:${userId}:${sid}`);
          return data ? { sessionId: sid, ...JSON.parse(data) } : null;
        })
      );

      const validSessions = sessionDetails.filter(s => s !== null);
      validSessions.sort((a, b) => a.lastActivity - b.lastActivity);

      // Remove excess sessions
      for (let i = 0; i < validSessions.length - MAX_SESSIONS; i++) {
        const oldSession = validSessions[i];
        await redis.del(`session:${userId}:${oldSession.sessionId}`);
        await redis.srem(userSessionsKey, oldSession.sessionId);
      }
    }

    console.log(`Session created for user ${userId}: ${sessionId}`);

    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        sessionId,
        expiresAt: sessionData.expiresAt
      })
    };

  } catch (error) {
    console.error('Error creating session:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to create session' })
    };
  }
}

/**
 * Validate session
 */
async function validateSession(redis, { userId, sessionId, deviceFingerprint }) {
  try {
    if (!userId || !sessionId) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'userId and sessionId are required' })
      };
    }

    const sessionKey = `session:${userId}:${sessionId}`;
    const sessionData = await redis.get(sessionKey);

    if (!sessionData) {
      return {
        statusCode: 401,
        body: JSON.stringify({
          valid: false,
          reason: 'Session not found'
        })
      };
    }

    const session = JSON.parse(sessionData);
    const now = Date.now();

    // Check expiry
    if (now > session.expiresAt) {
      await redis.del(sessionKey);
      return {
        statusCode: 401,
        body: JSON.stringify({
          valid: false,
          reason: 'Session expired'
        })
      };
    }

    // Check idle timeout (30 minutes)
    const idleTimeout = 30 * 60 * 1000;
    if (now - session.lastActivity > idleTimeout) {
      await redis.del(sessionKey);
      return {
        statusCode: 401,
        body: JSON.stringify({
          valid: false,
          reason: 'Session idle timeout'
        })
      };
    }

    // Check device fingerprint if provided
    if (deviceFingerprint && session.deviceFingerprint !== deviceFingerprint) {
      console.warn(`Device fingerprint mismatch for session ${sessionId}`);
      return {
        statusCode: 401,
        body: JSON.stringify({
          valid: false,
          reason: 'Device fingerprint mismatch'
        })
      };
    }

    // Update last activity
    session.lastActivity = now;
    await redis.setex(sessionKey, 86400, JSON.stringify(session));

    return {
      statusCode: 200,
      body: JSON.stringify({
        valid: true,
        session: {
          userId: session.userId,
          sessionId: session.sessionId,
          createdAt: session.createdAt,
          lastActivity: session.lastActivity,
          expiresAt: session.expiresAt
        }
      })
    };

  } catch (error) {
    console.error('Error validating session:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to validate session' })
    };
  }
}

/**
 * Update session metadata
 */
async function updateSession(redis, { userId, sessionId, metadata }) {
  try {
    const sessionKey = `session:${userId}:${sessionId}`;
    const sessionData = await redis.get(sessionKey);

    if (!sessionData) {
      return {
        statusCode: 404,
        body: JSON.stringify({ error: 'Session not found' })
      };
    }

    const session = JSON.parse(sessionData);
    const updatedSession = {
      ...session,
      ...metadata,
      lastActivity: Date.now(),
      version: (session.version || 1) + 1
    };

    await redis.setex(sessionKey, 86400, JSON.stringify(updatedSession));

    return {
      statusCode: 200,
      body: JSON.stringify({ success: true })
    };

  } catch (error) {
    console.error('Error updating session:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to update session' })
    };
  }
}

/**
 * Update session activity timestamp
 */
async function updateActivity(redis, { userId, sessionId }) {
  try {
    const sessionKey = `session:${userId}:${sessionId}`;
    const sessionData = await redis.get(sessionKey);

    if (!sessionData) {
      return {
        statusCode: 404,
        body: JSON.stringify({ error: 'Session not found' })
      };
    }

    const session = JSON.parse(sessionData);
    session.lastActivity = Date.now();

    await redis.setex(sessionKey, 86400, JSON.stringify(session));

    return {
      statusCode: 200,
      body: JSON.stringify({ success: true })
    };

  } catch (error) {
    console.error('Error updating activity:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to update activity' })
    };
  }
}

/**
 * Revoke session
 */
async function revokeSession(redis, { userId, sessionId, revokeAll = false }) {
  try {
    if (revokeAll) {
      // Revoke all sessions for user
      const userSessionsKey = `user:${userId}:sessions`;
      const sessions = await redis.smembers(userSessionsKey);

      const pipeline = redis.pipeline();
      sessions.forEach(sid => {
        pipeline.del(`session:${userId}:${sid}`);
      });
      pipeline.del(userSessionsKey);
      await pipeline.exec();

      return {
        statusCode: 200,
        body: JSON.stringify({
          success: true,
          revokedSessions: sessions.length
        })
      };
    } else {
      // Revoke specific session
      const sessionKey = `session:${userId}:${sessionId}`;
      const userSessionsKey = `user:${userId}:sessions`;

      await redis.del(sessionKey);
      await redis.srem(userSessionsKey, sessionId);

      return {
        statusCode: 200,
        body: JSON.stringify({ success: true })
      };
    }

  } catch (error) {
    console.error('Error revoking session:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to revoke session' })
    };
  }
}

/**
 * Get session status
 */
async function getSessionStatus(redis, { userId, sessionId }) {
  try {
    if (!userId || !sessionId) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'userId and sessionId are required' })
      };
    }

    const sessionKey = `session:${userId}:${sessionId}`;
    const sessionData = await redis.get(sessionKey);

    if (!sessionData) {
      return {
        statusCode: 404,
        body: JSON.stringify({ error: 'Session not found' })
      };
    }

    const session = JSON.parse(sessionData);
    const now = Date.now();

    return {
      statusCode: 200,
      body: JSON.stringify({
        sessionId: session.sessionId,
        userId: session.userId,
        createdAt: session.createdAt,
        lastActivity: session.lastActivity,
        expiresAt: session.expiresAt,
        timeToExpiry: Math.max(0, session.expiresAt - now),
        isValid: now <= session.expiresAt && (now - session.lastActivity) <= 30 * 60 * 1000
      })
    };

  } catch (error) {
    console.error('Error getting session status:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to get session status' })
    };
  }
}

/**
 * List user sessions
 */
async function listUserSessions(redis, { userId }) {
  try {
    if (!userId) {
      return {
        statusCode: 400,
        body: JSON.stringify({ error: 'userId is required' })
      };
    }

    const userSessionsKey = `user:${userId}:sessions`;
    const sessionIds = await redis.smembers(userSessionsKey);

    const sessions = await Promise.all(
      sessionIds.map(async (sessionId) => {
        const sessionData = await redis.get(`session:${userId}:${sessionId}`);
        if (sessionData) {
          const session = JSON.parse(sessionData);
          return {
            sessionId: session.sessionId,
            createdAt: session.createdAt,
            lastActivity: session.lastActivity,
            expiresAt: session.expiresAt,
            deviceFingerprint: session.deviceFingerprint
          };
        }
        return null;
      })
    );

    const validSessions = sessions.filter(s => s !== null);

    return {
      statusCode: 200,
      body: JSON.stringify({
        userId,
        sessionCount: validSessions.length,
        sessions: validSessions
      })
    };

  } catch (error) {
    console.error('Error listing sessions:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to list sessions' })
    };
  }
}

/**
 * Cleanup expired sessions
 */
async function cleanupExpiredSessions(redis, { userId }) {
  try {
    const userSessionsKey = `user:${userId}:sessions`;
    const sessionIds = await redis.smembers(userSessionsKey);
    const now = Date.now();
    let cleanedCount = 0;

    for (const sessionId of sessionIds) {
      const sessionKey = `session:${userId}:${sessionId}`;
      const sessionData = await redis.get(sessionKey);

      if (!sessionData) {
        // Session key doesn't exist, remove from set
        await redis.srem(userSessionsKey, sessionId);
        cleanedCount++;
        continue;
      }

      const session = JSON.parse(sessionData);

      // Check if expired or idle
      const isExpired = now > session.expiresAt;
      const isIdle = (now - session.lastActivity) > 30 * 60 * 1000;

      if (isExpired || isIdle) {
        await redis.del(sessionKey);
        await redis.srem(userSessionsKey, sessionId);
        cleanedCount++;
      }
    }

    return {
      statusCode: 200,
      body: JSON.stringify({
        success: true,
        cleanedSessions: cleanedCount
      })
    };

  } catch (error) {
    console.error('Error cleaning up sessions:', error);
    return {
      statusCode: 500,
      body: JSON.stringify({ error: 'Failed to cleanup sessions' })
    };
  }
}