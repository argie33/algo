// Compliance Routes
// API endpoints for compliance monitoring, GDPR requests, and audit logging

const express = require('express');
const router = express.Router();
const ComplianceService = require('../services/complianceService');

// Initialize compliance service
const complianceService = new ComplianceService();

// Generate compliance report
router.get('/reports/:framework', async (req, res) => {
  try {
    const { framework } = req.params;
    const { startDate, endDate, includeDetails = false } = req.query;
    
    const supportedFrameworks = ['GDPR', 'SOX', 'PCI_DSS', 'FINRA', 'SEC'];
    
    if (!supportedFrameworks.includes(framework.toUpperCase())) {
      return res.status(400).json({
        success: false,
        error: 'Unsupported compliance framework',
        message: `Supported frameworks: ${supportedFrameworks.join(', ')}`
      });
    }
    
    const options = {
      startDate,
      endDate,
      includeDetails: includeDetails === 'true'
    };
    
    const report = complianceService.generateComplianceReport(
      framework.toUpperCase(), 
      options
    );
    
    res.json({
      success: true,
      data: report,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Compliance report generation failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to generate compliance report',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Data subject access request (GDPR Article 15)
router.post('/data-subject/access-request', async (req, res) => {
  try {
    const { userId, categories, requestData = {} } = req.body;
    
    if (!userId) {
      return res.status(400).json({
        success: false,
        error: 'Missing required field',
        message: 'userId is required'
      });
    }
    
    const enhancedRequestData = {
      ...requestData,
      categories,
      ipAddress: req.ip,
      userAgent: req.get('User-Agent'),
      timestamp: new Date().toISOString()
    };
    
    const result = await complianceService.handleDataSubjectAccessRequest(
      userId, 
      enhancedRequestData
    );
    
    res.json({
      success: true,
      data: {
        requestId: result.requestId,
        status: result.status,
        deliveryMethod: result.deliveryMethod,
        expiresAt: result.expiresAt,
        message: 'Data access request processed successfully'
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Data access request failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process data access request',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Data subject deletion request (GDPR Article 17)
router.post('/data-subject/deletion-request', async (req, res) => {
  try {
    const { userId, reason, requestData = {} } = req.body;
    
    if (!userId) {
      return res.status(400).json({
        success: false,
        error: 'Missing required field',
        message: 'userId is required'
      });
    }
    
    const enhancedRequestData = {
      ...requestData,
      reason,
      ipAddress: req.ip,
      userAgent: req.get('User-Agent'),
      timestamp: new Date().toISOString()
    };
    
    const result = await complianceService.handleDataDeletionRequest(
      userId, 
      enhancedRequestData
    );
    
    res.json({
      success: true,
      data: {
        requestId: result.requestId,
        status: result.status,
        deletionPlan: result.deletionPlan,
        retainedData: result.retainedData,
        message: result.status === 'processed' 
          ? 'Data deletion request processed successfully'
          : `Data deletion request ${result.status}: ${result.reason}`
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Data deletion request failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to process data deletion request',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Record user consent
router.post('/consent', async (req, res) => {
  try {
    const { 
      userId, 
      consentType, 
      purposes, 
      consentGiven,
      consentMethod = 'explicit',
      expiresAt 
    } = req.body;
    
    if (!userId || !consentType || !purposes || consentGiven === undefined) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'userId, consentType, purposes, and consentGiven are required'
      });
    }
    
    const consentData = {
      userId,
      consentType,
      purposes: Array.isArray(purposes) ? purposes : [purposes],
      lawfulBasis: 'Consent',
      consentGiven,
      consentMethod,
      ipAddress: req.ip,
      userAgent: req.get('User-Agent'),
      expiresAt
    };
    
    const consentRecord = complianceService.recordConsent(consentData);
    
    res.json({
      success: true,
      data: {
        consentId: consentRecord.id,
        userId: '[REDACTED]',
        consentType: consentRecord.consentType,
        consentGiven: consentRecord.consentGiven,
        purposes: consentRecord.purposes,
        timestamp: consentRecord.timestamp
      },
      message: 'Consent recorded successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Consent recording failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to record consent',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Withdraw consent
router.post('/consent/:consentId/withdraw', async (req, res) => {
  try {
    const { consentId } = req.params;
    const { reason, method = 'user_request' } = req.body;
    
    const withdrawalData = {
      reason,
      method,
      ipAddress: req.ip,
      userAgent: req.get('User-Agent'),
      timestamp: new Date().toISOString()
    };
    
    const updatedConsent = complianceService.withdrawConsent(consentId, withdrawalData);
    
    res.json({
      success: true,
      data: {
        consentId,
        withdrawnAt: updatedConsent.withdrawnAt,
        withdrawalMethod: updatedConsent.withdrawalMethod,
        withdrawalReason: updatedConsent.withdrawalReason
      },
      message: 'Consent withdrawn successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Consent withdrawal failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to withdraw consent',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Record data processing activity
router.post('/data-processing', async (req, res) => {
  try {
    const {
      dataType,
      purpose,
      legalBasis,
      dataSubjects,
      categories,
      recipients = [],
      retentionPeriod,
      securityMeasures = [],
      transferDetails = null,
      automatedDecisionMaking = false
    } = req.body;
    
    if (!dataType || !purpose || !legalBasis || !dataSubjects) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'dataType, purpose, legalBasis, and dataSubjects are required'
      });
    }
    
    const activity = {
      dataType,
      purpose,
      legalBasis,
      dataSubjects: Array.isArray(dataSubjects) ? dataSubjects : [dataSubjects],
      categories: Array.isArray(categories) ? categories : [categories],
      recipients,
      retentionPeriod,
      securityMeasures,
      transferDetails,
      automatedDecisionMaking
    };
    
    const processingRecord = complianceService.recordDataProcessing(activity);
    
    res.json({
      success: true,
      data: {
        activityId: processingRecord.id,
        dataType: processingRecord.dataType,
        purpose: processingRecord.purpose,
        legalBasis: processingRecord.legalBasis,
        timestamp: processingRecord.timestamp
      },
      message: 'Data processing activity recorded successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Data processing recording failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to record data processing activity',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Report data breach (GDPR Article 33)
router.post('/data-breach', async (req, res) => {
  try {
    const {
      type,
      severity,
      affectedDataTypes,
      affectedDataSubjects,
      cause,
      containmentMeasures,
      riskAssessment
    } = req.body;
    
    if (!type || !severity || !affectedDataTypes || !affectedDataSubjects) {
      return res.status(400).json({
        success: false,
        error: 'Missing required fields',
        message: 'type, severity, affectedDataTypes, and affectedDataSubjects are required'
      });
    }
    
    const breachData = {
      type,
      severity,
      affectedDataTypes: Array.isArray(affectedDataTypes) ? affectedDataTypes : [affectedDataTypes],
      affectedDataSubjects: parseInt(affectedDataSubjects),
      cause,
      containmentMeasures: Array.isArray(containmentMeasures) ? containmentMeasures : [containmentMeasures],
      riskAssessment
    };
    
    const breach = complianceService.reportDataBreach(breachData);
    
    res.json({
      success: true,
      data: {
        breachId: breach.id,
        detectedAt: breach.detectedAt,
        severity: breach.severity,
        notificationRequired: breach.notificationRequired,
        affectedDataSubjects: breach.affectedDataSubjects
      },
      message: 'Data breach reported successfully',
      urgent: breach.notificationRequired,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Data breach reporting failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to report data breach',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Apply data retention policy
router.post('/retention/:dataType/apply', async (req, res) => {
  try {
    const { dataType } = req.params;
    
    const result = complianceService.applyRetentionPolicy(dataType);
    
    res.json({
      success: true,
      data: {
        dataType,
        policyApplied: result.policyApplied.name,
        cutoffDate: result.cutoffDate,
        dataMarkedForDeletion: result.dataMarkedForDeletion
      },
      message: 'Data retention policy applied successfully',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Retention policy application failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to apply retention policy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get compliance dashboard
router.get('/dashboard', async (req, res) => {
  try {
    const dashboard = complianceService.getComplianceDashboard();
    
    res.json({
      success: true,
      data: dashboard,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Compliance dashboard failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get compliance dashboard',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get audit logs (admin only)
router.get('/audit-logs', async (req, res) => {
  try {
    const { limit = 50, userId, action, startDate, endDate } = req.query;
    
    let logs = [...complianceService.auditLogs];
    
    // Filter by user
    if (userId) {
      logs = logs.filter(log => log.userId === userId);
    }
    
    // Filter by action
    if (action) {
      logs = logs.filter(log => log.action.includes(action.toUpperCase()));
    }
    
    // Filter by date range
    if (startDate) {
      const start = new Date(startDate);
      logs = logs.filter(log => new Date(log.timestamp) >= start);
    }
    
    if (endDate) {
      const end = new Date(endDate);
      logs = logs.filter(log => new Date(log.timestamp) <= end);
    }
    
    // Sort by most recent and limit
    logs = logs
      .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
      .slice(0, parseInt(limit));
    
    // Redact sensitive information
    const sanitizedLogs = logs.map(log => ({
      ...log,
      userId: log.userId === 'system' ? 'system' : '[REDACTED]',
      details: {
        ...log.details,
        userId: log.details.userId ? '[REDACTED]' : undefined
      }
    }));
    
    res.json({
      success: true,
      data: {
        logs: sanitizedLogs,
        count: sanitizedLogs.length,
        totalLogs: complianceService.auditLogs.length,
        filters: { limit, userId: userId ? '[REDACTED]' : undefined, action, startDate, endDate }
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Audit logs retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to retrieve audit logs',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get supported compliance frameworks
router.get('/frameworks', async (req, res) => {
  try {
    const frameworks = Object.entries(complianceService.complianceFrameworks).map(
      ([code, name]) => ({ code, name })
    );
    
    res.json({
      success: true,
      data: frameworks,
      count: frameworks.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Frameworks retrieval failed:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to get compliance frameworks',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Health check
router.get('/health', async (req, res) => {
  try {
    // Test core compliance functions
    const testAuditLog = complianceService.logAuditEvent({
      action: 'HEALTH_CHECK',
      resource: 'compliance_service',
      details: { test: true },
      userId: 'system'
    });
    
    const testReport = complianceService.generateComplianceReport('GDPR', {
      startDate: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(),
      endDate: new Date().toISOString()
    });
    
    const dashboard = complianceService.getComplianceDashboard();
    
    res.json({
      success: true,
      message: 'Compliance services operational',
      services: {
        auditLogging: {
          status: testAuditLog ? 'operational' : 'error',
          eventCount: complianceService.auditLogs.length
        },
        complianceReporting: {
          status: testReport ? 'operational' : 'error',
          frameworks: Object.keys(complianceService.complianceFrameworks).length
        },
        gdprCompliance: {
          status: 'operational',
          features: ['data access requests', 'data deletion', 'consent management', 'breach reporting']
        },
        dataRetention: {
          status: 'operational',
          policies: complianceService.dataRetentionPolicies.size
        },
        dashboard: {
          status: dashboard ? 'operational' : 'error',
          complianceScore: dashboard.summary.complianceScore
        }
      },
      statistics: {
        auditEvents: complianceService.auditLogs.length,
        consentRecords: complianceService.consentRecords.size,
        retentionPolicies: complianceService.dataRetentionPolicies.size,
        dataProcessingActivities: complianceService.dataProcessingActivities.length,
        breachNotifications: complianceService.breachNotifications.length
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Compliance health check failed:', error);
    res.status(503).json({
      success: false,
      error: 'Compliance services unhealthy',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;