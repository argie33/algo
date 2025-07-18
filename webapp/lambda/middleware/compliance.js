// Compliance Middleware
// Automatic audit logging for GDPR and financial compliance requirements

const ComplianceService = require('../services/complianceService');

class ComplianceMiddleware {
  constructor() {
    this.complianceService = new ComplianceService();
  }

  // Audit logging middleware for API endpoints
  auditMiddleware() {
    return (req, res, next) => {
      const originalJson = res.json;
      const originalSend = res.send;
      
      // Capture response data
      res.json = function(body) {
        res.responseData = body;
        return originalJson.call(this, body);
      };
      
      res.send = function(body) {
        res.responseData = body;
        return originalSend.call(this, body);
      };
      
      // Log the request after response is sent
      res.on('finish', () => {
        this.logAPIRequest(req, res);
      });
      
      next();
    };
  }

  // Log API requests for compliance audit
  logAPIRequest(req, res) {
    const sensitiveEndpoints = [
      '/api/settings',
      '/api/auth',
      '/api/portfolio',
      '/api/trading',
      '/api/compliance'
    ];
    
    const isSensitive = sensitiveEndpoints.some(endpoint => 
      req.path.startsWith(endpoint)
    );
    
    if (isSensitive || res.statusCode >= 400) {
      const auditData = {
        userId: req.user?.id || req.headers['x-user-id'] || 'anonymous',
        action: `${req.method}_${req.path.replace(/\/api\//, '').toUpperCase()}`,
        resource: this.getResourceFromPath(req.path),
        details: {
          method: req.method,
          path: req.path,
          statusCode: res.statusCode,
          userAgent: req.get('User-Agent'),
          responseTime: res.getHeaders()['x-response-time'],
          bodySize: req.headers['content-length'] || 0,
          queryParams: Object.keys(req.query).length > 0 ? '[PRESENT]' : 'none',
          hasBody: req.body && Object.keys(req.body).length > 0,
          success: res.statusCode < 400
        },
        ipAddress: req.ip,
        userAgent: req.get('User-Agent'),
        sessionId: req.sessionID || req.headers['x-session-id'],
        success: res.statusCode < 400,
        riskLevel: this.assessRequestRisk(req, res),
        complianceFramework: ['GDPR', 'SOX', 'FINRA']
      };
      
      this.complianceService.logAuditEvent(auditData);
    }
  }

  // Extract resource name from API path
  getResourceFromPath(path) {
    const pathParts = path.split('/').filter(Boolean);
    if (pathParts.length >= 2) {
      return pathParts[1]; // Return the resource part after /api/
    }
    return 'unknown';
  }

  // Assess risk level of the request
  assessRequestRisk(req, res) {
    if (res.statusCode >= 500) return 'HIGH';
    if (res.statusCode >= 400) return 'MEDIUM';
    
    const highRiskPaths = [
      '/api/settings/api-keys',
      '/api/auth/login',
      '/api/compliance/data-subject',
      '/api/trading'
    ];
    
    if (highRiskPaths.some(path => req.path.startsWith(path))) {
      return 'HIGH';
    }
    
    if (req.method !== 'GET') return 'MEDIUM';
    
    return 'LOW';
  }

  // Data processing activity logging middleware
  dataProcessingMiddleware() {
    return (req, res, next) => {
      // Monitor data processing activities
      if (req.method !== 'GET' && req.body) {
        const hasPersonalData = this.containsPersonalData(req.body);
        
        if (hasPersonalData) {
          const activity = {
            dataType: this.identifyDataType(req.path, req.body),
            purpose: this.identifyProcessingPurpose(req.path, req.method),
            legalBasis: this.determineLegalBasis(req.path),
            dataSubjects: this.extractDataSubjects(req),
            categories: this.classifyDataCategories(req.body),
            securityMeasures: ['HTTPS', 'Authentication', 'Input Validation'],
            automatedDecisionMaking: this.hasAutomatedDecisionMaking(req.path)
          };
          
          this.complianceService.recordDataProcessing(activity);
        }
      }
      
      next();
    };
  }

  // Check if request contains personal data
  containsPersonalData(body) {
    const personalDataFields = [
      'email', 'name', 'firstName', 'lastName', 'phone', 'address',
      'dateOfBirth', 'ssn', 'userId', 'accountNumber'
    ];
    
    const bodyString = JSON.stringify(body).toLowerCase();
    return personalDataFields.some(field => bodyString.includes(field));
  }

  // Identify data type being processed
  identifyDataType(path, body) {
    if (path.includes('/auth')) return 'authentication_data';
    if (path.includes('/settings')) return 'user_preferences';
    if (path.includes('/portfolio')) return 'financial_data';
    if (path.includes('/trading')) return 'transaction_data';
    if (path.includes('/compliance')) return 'compliance_data';
    return 'user_data';
  }

  // Identify processing purpose
  identifyProcessingPurpose(path, method) {
    const purposes = {
      'POST': 'Data Creation',
      'PUT': 'Data Update',
      'PATCH': 'Data Modification',
      'DELETE': 'Data Deletion'
    };
    
    if (path.includes('/auth')) return 'User Authentication';
    if (path.includes('/portfolio')) return 'Portfolio Management';
    if (path.includes('/trading')) return 'Trade Execution';
    if (path.includes('/settings')) return 'User Preferences Management';
    
    return purposes[method] || 'Data Processing';
  }

  // Determine legal basis for processing
  determineLegalBasis(path) {
    if (path.includes('/auth')) return 'Contract';
    if (path.includes('/trading')) return 'Contract';
    if (path.includes('/compliance')) return 'Legal Obligation';
    return 'Legitimate Interest';
  }

  // Extract data subjects from request
  extractDataSubjects(req) {
    const userId = req.user?.id || req.headers['x-user-id'];
    return userId ? [userId] : ['anonymous'];
  }

  // Classify data categories
  classifyDataCategories(body) {
    const categories = [];
    const bodyString = JSON.stringify(body).toLowerCase();
    
    if (bodyString.includes('email') || bodyString.includes('name')) {
      categories.push('Identity Data');
    }
    if (bodyString.includes('phone') || bodyString.includes('address')) {
      categories.push('Contact Data');
    }
    if (bodyString.includes('account') || bodyString.includes('portfolio')) {
      categories.push('Financial Data');
    }
    if (bodyString.includes('preference') || bodyString.includes('setting')) {
      categories.push('Preference Data');
    }
    
    return categories.length > 0 ? categories : ['User Data'];
  }

  // Check for automated decision making
  hasAutomatedDecisionMaking(path) {
    const automatedPaths = [
      '/api/algo',
      '/api/portfolio-optimization',
      '/api/technical',
      '/api/screener'
    ];
    
    return automatedPaths.some(autoPath => path.startsWith(autoPath));
  }

  // GDPR consent validation middleware
  consentValidationMiddleware() {
    return (req, res, next) => {
      // Check for consent requirements on data processing endpoints
      if (req.method !== 'GET' && this.requiresConsent(req.path)) {
        const hasConsent = req.headers['x-user-consent'] === 'true' ||
                          req.body?.hasConsent === true;
        
        if (!hasConsent) {
          // Log consent requirement
          this.complianceService.logAuditEvent({
            userId: req.user?.id || 'anonymous',
            action: 'CONSENT_REQUIRED',
            resource: 'data_processing',
            details: {
              path: req.path,
              method: req.method,
              reason: 'User consent required for data processing'
            },
            ipAddress: req.ip,
            riskLevel: 'MEDIUM',
            complianceFramework: ['GDPR']
          });
          
          return res.status(403).json({
            success: false,
            error: 'Consent required',
            message: 'User consent is required for this data processing activity',
            consentRequired: true,
            dataProcessingPurpose: this.identifyProcessingPurpose(req.path, req.method)
          });
        }
      }
      
      next();
    };
  }

  // Check if endpoint requires explicit consent
  requiresConsent(path) {
    const consentRequiredPaths = [
      '/api/settings/notifications',
      '/api/portfolio/create',
      '/api/trading',
      '/api/compliance/data-processing'
    ];
    
    return consentRequiredPaths.some(consentPath => path.startsWith(consentPath));
  }

  // Data retention cleanup middleware
  retentionCleanupMiddleware() {
    return (req, res, next) => {
      // Trigger retention policy cleanup periodically
      const shouldCleanup = Math.random() < 0.01; // 1% chance per request
      
      if (shouldCleanup) {
        process.nextTick(() => {
          try {
            const retentionTypes = ['session_data', 'temporary_data'];
            retentionTypes.forEach(type => {
              this.complianceService.applyRetentionPolicy(type);
            });
          } catch (error) {
            console.error('Retention cleanup failed:', error);
          }
        });
      }
      
      next();
    };
  }

  // Get compliance service instance
  getComplianceService() {
    return this.complianceService;
  }
}

module.exports = ComplianceMiddleware;