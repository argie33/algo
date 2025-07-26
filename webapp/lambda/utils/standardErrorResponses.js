/**
 * Standardized Error Response Utility
 * Provides consistent error response structures across all API endpoints
 */

const createStandardError = (type, message, details = {}) => {
  const timestamp = new Date().toISOString();
  const errorId = `error-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;

  return {
    success: false,
    error: type,
    message,
    details: {
      ...details,
      errorId,
      timestamp
    }
  };
};

const createServiceUnavailableError = (serviceName, details = {}) => {
  return createStandardError(
    `${serviceName} Service Unavailable`,
    `${serviceName} service is currently unavailable`,
    {
      type: 'SERVICE_UNAVAILABLE',
      service: serviceName.toLowerCase(),
      troubleshooting: {
        immediate: [
          'Check system status page',
          'Verify service configuration',
          'Try again in a few minutes'
        ],
        advanced: [
          'Check service logs',
          'Verify dependencies',
          'Contact system administrator'
        ]
      },
      support: {
        status_page: '/status',
        documentation: '/help',
        contact: '/support'
      },
      ...details
    }
  );
};

const createNotImplementedError = (featureName, details = {}) => {
  return createStandardError(
    `${featureName} Not Implemented`,
    `${featureName} feature is not yet implemented`,
    {
      type: 'FEATURE_NOT_IMPLEMENTED',
      feature: featureName.toLowerCase().replace(/\s+/g, '_'),
      implementation_status: 'planned',
      alternative_approaches: [],
      future_features: [],
      ...details
    }
  );
};

const createConfigurationError = (configType, details = {}) => {
  return createStandardError(
    `${configType} Configuration Required`,
    `${configType} must be properly configured to access this feature`,
    {
      type: 'CONFIGURATION_REQUIRED',
      configuration_type: configType.toLowerCase().replace(/\s+/g, '_'),
      setup_required: true,
      setup_url: '/settings',
      ...details
    }
  );
};

const createAuthenticationError = (details = {}) => {
  return createStandardError(
    'Authentication Required',
    'Valid authentication credentials are required to access this resource',
    {
      type: 'AUTHENTICATION_REQUIRED',
      authentication_methods: ['Bearer token', 'API key'],
      documentation: '/help/authentication',
      ...details
    }
  );
};

const createValidationError = (field, reason, details = {}) => {
  return createStandardError(
    'Validation Error',
    `Validation failed for field: ${field}`,
    {
      type: 'VALIDATION_ERROR',
      field,
      reason,
      validation_rules: {},
      ...details
    }
  );
};

const createInternalServerError = (operation, error, details = {}) => {
  return createStandardError(
    'Internal Server Error',
    `Internal error occurred during ${operation}`,
    {
      type: 'INTERNAL_SERVER_ERROR',
      operation,
      error_details: error?.message || 'Unknown error',
      escalation_required: true,
      ...details
    }
  );
};

// HTTP Status Code helpers
const sendServiceUnavailable = (res, serviceName, details = {}) => {
  return res.status(503).json(createServiceUnavailableError(serviceName, details));
};

const sendNotImplemented = (res, featureName, details = {}) => {
  return res.status(501).json(createNotImplementedError(featureName, details));
};

const sendConfigurationRequired = (res, configType, details = {}) => {
  return res.status(400).json(createConfigurationError(configType, details));
};

const sendAuthenticationRequired = (res, details = {}) => {
  return res.status(401).json(createAuthenticationError(details));
};

const sendValidationError = (res, field, reason, details = {}) => {
  return res.status(400).json(createValidationError(field, reason, details));
};

const sendInternalServerError = (res, operation, error, details = {}) => {
  return res.status(500).json(createInternalServerError(operation, error, details));
};

module.exports = {
  // Error creators
  createStandardError,
  createServiceUnavailableError,
  createNotImplementedError,
  createConfigurationError,
  createAuthenticationError,
  createValidationError,
  createInternalServerError,
  
  // Response helpers
  sendServiceUnavailable,
  sendNotImplemented,
  sendConfigurationRequired,
  sendAuthenticationRequired,
  sendValidationError,
  sendInternalServerError
};