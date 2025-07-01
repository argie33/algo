const { CognitoJwtVerifier } = require('aws-jwt-verify');

// Create JWT verifier for Cognito User Pool
const verifier = CognitoJwtVerifier.create({
  userPoolId: process.env.COGNITO_USER_POOL_ID,
  tokenUse: 'access',
  clientId: process.env.COGNITO_CLIENT_ID,
});

// Authentication middleware
const authenticateToken = async (req, res, next) => {
  try {
    // Skip authentication in development mode
    if (process.env.NODE_ENV === 'development' && process.env.SKIP_AUTH === 'true') {
      req.user = {
        sub: 'dev-user',
        email: 'dev@example.com',
        username: 'dev-user',
        role: 'admin'
      };
      return next();
    }

    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1]; // Bearer TOKEN

    if (!token) {
      return res.status(401).json({
        error: 'Authentication required',
        message: 'Access token is missing from Authorization header'
      });
    }

    // Verify the JWT token
    const payload = await verifier.verify(token);
    
    // Add user information to request
    req.user = {
      sub: payload.sub,
      email: payload.email,
      username: payload.username,
      role: payload['custom:role'] || 'user',
      groups: payload['cognito:groups'] || []
    };

    next();
  } catch (error) {
    console.error('Authentication error:', error);
    
    // Handle specific JWT errors
    if (error.name === 'TokenExpiredError') {
      return res.status(401).json({
        error: 'Token expired',
        message: 'Your session has expired. Please log in again.'
      });
    }
    
    if (error.name === 'JsonWebTokenError') {
      return res.status(401).json({
        error: 'Invalid token',
        message: 'The provided token is invalid.'
      });
    }

    return res.status(401).json({
      error: 'Authentication failed',
      message: 'Could not verify authentication token'
    });
  }
};

// Authorization middleware for role-based access
const requireRole = (roles) => {
  return (req, res, next) => {
    if (!req.user) {
      return res.status(401).json({
        error: 'Authentication required',
        message: 'User must be authenticated to access this resource'
      });
    }

    const userRole = req.user.role;
    const userGroups = req.user.groups || [];
    
    // Check if user has required role or is in required group
    const hasRole = roles.includes(userRole);
    const hasGroup = roles.some(role => userGroups.includes(role));
    
    if (!hasRole && !hasGroup) {
      return res.status(403).json({
        error: 'Insufficient permissions',
        message: `Access denied. Required roles: ${roles.join(', ')}`
      });
    }

    next();
  };
};

// Optional authentication middleware (doesn't fail if no token)
const optionalAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers['authorization'];
    const token = authHeader && authHeader.split(' ')[1];

    if (token) {
      const payload = await verifier.verify(token);
      req.user = {
        sub: payload.sub,
        email: payload.email,
        username: payload.username,
        role: payload['custom:role'] || 'user',
        groups: payload['cognito:groups'] || []
      };
    }
  } catch (error) {
    // Silently continue without authentication
    console.log('Optional auth failed:', error.message);
  }
  
  next();
};

module.exports = {
  authenticateToken,
  requireRole,
  optionalAuth
};