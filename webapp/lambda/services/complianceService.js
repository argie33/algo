// Compliance Service
// Implements compliance reporting, data retention policies, and GDPR compliance

const crypto = require('crypto');

class ComplianceService {
  constructor() {
    this.auditLogs = [];
    this.dataRetentionPolicies = new Map();
    this.consentRecords = new Map();
    this.dataProcessingActivities = [];
    this.breachNotifications = [];
    
    // Initialize default retention policies
    this.initializeRetentionPolicies();
    
    // GDPR compliance settings
    this.gdprSettings = {
      dataControllerName: 'Financial Trading Platform',
      dataProtectionOfficer: 'dpo@tradingplatform.com',
      lawfulBasisForProcessing: 'Legitimate Interest',
      retentionPeriods: {
        'user_data': 7 * 365 * 24 * 60 * 60 * 1000, // 7 years
        'trading_data': 7 * 365 * 24 * 60 * 60 * 1000, // 7 years (regulatory requirement)
        'audit_logs': 3 * 365 * 24 * 60 * 60 * 1000, // 3 years
        'session_data': 30 * 24 * 60 * 60 * 1000, // 30 days
        'temporary_data': 24 * 60 * 60 * 1000 // 24 hours
      }
    };

    // Financial compliance frameworks
    this.complianceFrameworks = {
      'SOX': 'Sarbanes-Oxley Act',
      'MiFID_II': 'Markets in Financial Instruments Directive',
      'GDPR': 'General Data Protection Regulation',
      'CCPA': 'California Consumer Privacy Act',
      'PCI_DSS': 'Payment Card Industry Data Security Standard',
      'FINRA': 'Financial Industry Regulatory Authority',
      'SEC': 'Securities and Exchange Commission'
    };
  }

  // Initialize default data retention policies
  initializeRetentionPolicies() {
    const policies = [
      {
        id: 'user_data',
        name: 'User Personal Data',
        category: 'personal_data',
        retentionPeriod: this.gdprSettings.retentionPeriods.user_data,
        description: 'Personal information including name, email, contact details',
        legalBasis: 'Legitimate Interest',
        automatedDeletion: true
      },
      {
        id: 'trading_data',
        name: 'Trading and Financial Data',
        category: 'financial_data',
        retentionPeriod: this.gdprSettings.retentionPeriods.trading_data,
        description: 'Transaction records, portfolio data, trading history',
        legalBasis: 'Legal Obligation',
        automatedDeletion: false // Regulatory requirement - manual review needed
      },
      {
        id: 'audit_logs',
        name: 'Audit and Security Logs',
        category: 'security_data',
        retentionPeriod: this.gdprSettings.retentionPeriods.audit_logs,
        description: 'Security events, access logs, audit trails',
        legalBasis: 'Legitimate Interest',
        automatedDeletion: true
      },
      {
        id: 'session_data',
        name: 'Session and Temporary Data',
        category: 'temporary_data',
        retentionPeriod: this.gdprSettings.retentionPeriods.session_data,
        description: 'Session tokens, temporary cache, cookies',
        legalBasis: 'Legitimate Interest',
        automatedDeletion: true
      }
    ];

    policies.forEach(policy => {
      this.dataRetentionPolicies.set(policy.id, policy);
    });
  }

  // Log audit event
  logAuditEvent(event) {
    const auditEntry = {
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      userId: event.userId || 'system',
      action: event.action,
      resource: event.resource,
      details: event.details || {},
      ipAddress: event.ipAddress,
      userAgent: event.userAgent,
      sessionId: event.sessionId,
      success: event.success !== false,
      riskLevel: event.riskLevel || 'LOW',
      complianceFramework: event.complianceFramework || ['GDPR']
    };

    this.auditLogs.push(auditEntry);

    // Keep only recent audit logs in memory (last 1000)
    if (this.auditLogs.length > 1000) {
      this.auditLogs = this.auditLogs.slice(-1000);
    }

    console.log(`[AUDIT] ${auditEntry.action} by ${auditEntry.userId}:`, auditEntry.details);
    return auditEntry;
  }

  // Record data processing activity
  recordDataProcessing(activity) {
    const processingRecord = {
      id: crypto.randomUUID(),
      timestamp: new Date().toISOString(),
      dataType: activity.dataType,
      purpose: activity.purpose,
      legalBasis: activity.legalBasis,
      dataSubjects: activity.dataSubjects,
      categories: activity.categories,
      recipients: activity.recipients || [],
      retentionPeriod: activity.retentionPeriod,
      securityMeasures: activity.securityMeasures || [],
      transferDetails: activity.transferDetails || null,
      automatedDecisionMaking: activity.automatedDecisionMaking || false
    };

    this.dataProcessingActivities.push(processingRecord);

    // Log for compliance audit trail
    this.logAuditEvent({
      action: 'DATA_PROCESSING_RECORDED',
      resource: 'data_processing_activity',
      details: {
        activityId: processingRecord.id,
        dataType: activity.dataType,
        purpose: activity.purpose
      },
      complianceFramework: ['GDPR']
    });

    return processingRecord;
  }

  // Record user consent
  recordConsent(consentData) {
    const consentRecord = {
      id: crypto.randomUUID(),
      userId: consentData.userId,
      timestamp: new Date().toISOString(),
      consentType: consentData.consentType,
      purposes: consentData.purposes,
      lawfulBasis: consentData.lawfulBasis,
      consentGiven: consentData.consentGiven,
      consentMethod: consentData.consentMethod, // 'explicit', 'implied', 'opt-in', 'opt-out'
      ipAddress: consentData.ipAddress,
      userAgent: consentData.userAgent,
      withdrawnAt: null,
      expiresAt: consentData.expiresAt || null
    };

    this.consentRecords.set(consentRecord.id, consentRecord);

    // Log consent event
    this.logAuditEvent({
      userId: consentData.userId,
      action: consentData.consentGiven ? 'CONSENT_GIVEN' : 'CONSENT_WITHDRAWN',
      resource: 'user_consent',
      details: {
        consentId: consentRecord.id,
        consentType: consentData.consentType,
        purposes: consentData.purposes
      },
      ipAddress: consentData.ipAddress,
      userAgent: consentData.userAgent,
      complianceFramework: ['GDPR', 'CCPA']
    });

    return consentRecord;
  }

  // Withdraw consent
  withdrawConsent(consentId, withdrawalData) {
    const consentRecord = this.consentRecords.get(consentId);
    
    if (!consentRecord) {
      throw new Error('Consent record not found');
    }

    consentRecord.withdrawnAt = new Date().toISOString();
    consentRecord.withdrawalMethod = withdrawalData.method;
    consentRecord.withdrawalReason = withdrawalData.reason;

    // Log withdrawal
    this.logAuditEvent({
      userId: consentRecord.userId,
      action: 'CONSENT_WITHDRAWN',
      resource: 'user_consent',
      details: {
        consentId,
        originalConsent: consentRecord.consentType,
        withdrawalReason: withdrawalData.reason
      },
      ipAddress: withdrawalData.ipAddress,
      userAgent: withdrawalData.userAgent,
      complianceFramework: ['GDPR', 'CCPA']
    });

    return consentRecord;
  }

  // Handle data subject access request (GDPR Article 15)
  async handleDataSubjectAccessRequest(userId, requestData) {
    const requestId = crypto.randomUUID();
    
    // Log the request
    this.logAuditEvent({
      userId,
      action: 'DATA_ACCESS_REQUEST',
      resource: 'data_subject_rights',
      details: {
        requestId,
        requestType: 'access',
        requestedData: requestData.categories || 'all'
      },
      ipAddress: requestData.ipAddress,
      complianceFramework: ['GDPR']
    });

    // Collect user data (in a real implementation, this would query the database)
    const userData = {
      personalData: {
        userId: userId,
        email: '[REDACTED]',
        name: '[REDACTED]',
        registrationDate: '[REDACTED]',
        lastLogin: '[REDACTED]'
      },
      tradingData: {
        portfolioValue: '[REDACTED]',
        transactionCount: '[REDACTED]',
        apiKeys: '[REDACTED]'
      },
      consentRecords: Array.from(this.consentRecords.values())
        .filter(consent => consent.userId === userId),
      auditLogs: this.auditLogs
        .filter(log => log.userId === userId)
        .slice(-100), // Last 100 activities
      dataProcessingActivities: this.dataProcessingActivities
        .filter(activity => activity.dataSubjects.includes(userId))
    };

    // Generate data export
    const dataExport = {
      requestId,
      userId,
      exportDate: new Date().toISOString(),
      data: userData,
      format: 'JSON',
      dataController: this.gdprSettings.dataControllerName,
      legalBasis: 'GDPR Article 15 - Right of Access'
    };

    return {
      requestId,
      status: 'completed',
      dataExport,
      deliveryMethod: 'secure_download',
      expiresAt: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() // 30 days
    };
  }

  // Handle data deletion request (GDPR Article 17)
  async handleDataDeletionRequest(userId, requestData) {
    const requestId = crypto.randomUUID();
    
    // Log the request
    this.logAuditEvent({
      userId,
      action: 'DATA_DELETION_REQUEST',
      resource: 'data_subject_rights',
      details: {
        requestId,
        requestType: 'deletion',
        reason: requestData.reason
      },
      ipAddress: requestData.ipAddress,
      complianceFramework: ['GDPR']
    });

    // Check if deletion is possible (regulatory constraints)
    const deletionAssessment = this.assessDeletionRequest(userId, requestData);
    
    if (!deletionAssessment.canDelete) {
      return {
        requestId,
        status: 'rejected',
        reason: deletionAssessment.reason,
        legalBasis: deletionAssessment.legalBasis,
        alternativeActions: deletionAssessment.alternatives
      };
    }

    // In a real implementation, this would perform actual data deletion
    const deletionPlan = {
      personalData: 'SCHEDULED_FOR_DELETION',
      tradingData: 'RETAINED_LEGAL_OBLIGATION',
      sessionData: 'IMMEDIATE_DELETION',
      auditLogs: 'ANONYMIZED'
    };

    this.logAuditEvent({
      userId,
      action: 'DATA_DELETION_EXECUTED',
      resource: 'user_data',
      details: {
        requestId,
        deletionPlan
      },
      complianceFramework: ['GDPR']
    });

    return {
      requestId,
      status: 'processed',
      deletionPlan,
      completedAt: new Date().toISOString(),
      retainedData: deletionAssessment.retainedData
    };
  }

  // Assess whether data deletion request can be fulfilled
  assessDeletionRequest(userId, requestData) {
    // Financial services have specific retention requirements
    const hasActiveTrading = true; // Would check actual trading status
    const hasRegulatoryRetention = true; // Would check regulatory requirements

    if (hasRegulatoryRetention) {
      return {
        canDelete: false,
        reason: 'Regulatory retention requirements prevent full data deletion',
        legalBasis: 'Legal Obligation (Financial Services Regulations)',
        retainedData: ['trading_history', 'transaction_records', 'compliance_data'],
        alternatives: [
          'Anonymization of personal identifiers',
          'Restriction of processing for non-regulatory purposes',
          'Data portability for movable data'
        ]
      };
    }

    return {
      canDelete: true,
      reason: 'No legal obligations prevent deletion',
      retainedData: []
    };
  }

  // Generate compliance report
  generateComplianceReport(framework, options = {}) {
    const { startDate, endDate, includeDetails = false } = options;
    const now = new Date();
    const start = startDate ? new Date(startDate) : new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
    const end = endDate ? new Date(endDate) : now;

    // Filter audit logs by date range
    const relevantLogs = this.auditLogs.filter(log => {
      const logDate = new Date(log.timestamp);
      return logDate >= start && logDate <= end && 
             log.complianceFramework.includes(framework);
    });

    // Generate framework-specific report
    switch (framework) {
      case 'GDPR':
        return this.generateGDPRReport(relevantLogs, { start, end, includeDetails });
      case 'SOX':
        return this.generateSOXReport(relevantLogs, { start, end, includeDetails });
      case 'PCI_DSS':
        return this.generatePCIReport(relevantLogs, { start, end, includeDetails });
      default:
        return this.generateGenericComplianceReport(framework, relevantLogs, { start, end, includeDetails });
    }
  }

  // Generate GDPR compliance report
  generateGDPRReport(auditLogs, options) {
    const { start, end, includeDetails } = options;

    // Analyze GDPR compliance metrics
    const dataSubjectRequests = auditLogs.filter(log => 
      log.action.includes('DATA_ACCESS_REQUEST') || 
      log.action.includes('DATA_DELETION_REQUEST') ||
      log.action.includes('DATA_PORTABILITY_REQUEST')
    );

    const consentEvents = auditLogs.filter(log =>
      log.action.includes('CONSENT_GIVEN') ||
      log.action.includes('CONSENT_WITHDRAWN')
    );

    const dataBreaches = this.breachNotifications.filter(breach =>
      new Date(breach.detectedAt) >= start && new Date(breach.detectedAt) <= end
    );

    const dataProcessingCount = this.dataProcessingActivities.filter(activity =>
      new Date(activity.timestamp) >= start && new Date(activity.timestamp) <= end
    ).length;

    return {
      reportId: crypto.randomUUID(),
      framework: 'GDPR',
      generatedAt: new Date().toISOString(),
      period: {
        start: start.toISOString(),
        end: end.toISOString()
      },
      summary: {
        dataSubjectRequests: dataSubjectRequests.length,
        consentEvents: consentEvents.length,
        dataBreaches: dataBreaches.length,
        dataProcessingActivities: dataProcessingCount,
        complianceScore: this.calculateGDPRComplianceScore()
      },
      metrics: {
        requestFulfillmentTime: this.calculateAverageRequestTime(dataSubjectRequests),
        consentRate: this.calculateConsentRate(consentEvents),
        breachNotificationCompliance: this.calculateBreachComplianceRate(dataBreaches),
        dataMinimizationScore: this.assessDataMinimization()
      },
      details: includeDetails ? {
        dataSubjectRequests,
        consentEvents,
        dataBreaches,
        retentionPolicyCompliance: this.assessRetentionCompliance()
      } : null,
      recommendations: this.generateGDPRRecommendations()
    };
  }

  // Calculate GDPR compliance score
  calculateGDPRComplianceScore() {
    let score = 100;
    
    // Deduct points for various compliance issues
    const issues = this.identifyComplianceIssues();
    
    issues.forEach(issue => {
      switch (issue.severity) {
        case 'HIGH':
          score -= 25;
          break;
        case 'MEDIUM':
          score -= 10;
          break;
        case 'LOW':
          score -= 5;
          break;
      }
    });

    return Math.max(0, score);
  }

  // Identify compliance issues
  identifyComplianceIssues() {
    const issues = [];

    // Check for unresolved data subject requests
    const pendingRequests = this.auditLogs.filter(log =>
      log.action.includes('DATA_ACCESS_REQUEST') &&
      !this.auditLogs.some(resolve => 
        resolve.action.includes('DATA_ACCESS_FULFILLED') &&
        resolve.details.requestId === log.details.requestId
      )
    );

    if (pendingRequests.length > 0) {
      issues.push({
        type: 'PENDING_DATA_REQUESTS',
        severity: 'HIGH',
        description: `${pendingRequests.length} pending data subject requests`,
        count: pendingRequests.length
      });
    }

    // Check consent expiration
    const expiredConsents = Array.from(this.consentRecords.values()).filter(consent =>
      consent.expiresAt && new Date(consent.expiresAt) < new Date()
    );

    if (expiredConsents.length > 0) {
      issues.push({
        type: 'EXPIRED_CONSENTS',
        severity: 'MEDIUM',
        description: `${expiredConsents.length} expired consent records`,
        count: expiredConsents.length
      });
    }

    return issues;
  }

  // Generate GDPR recommendations
  generateGDPRRecommendations() {
    const issues = this.identifyComplianceIssues();
    const recommendations = [];

    issues.forEach(issue => {
      switch (issue.type) {
        case 'PENDING_DATA_REQUESTS':
          recommendations.push({
            priority: 'HIGH',
            action: 'Process pending data subject requests within 30 days',
            description: 'Fulfill outstanding data access and deletion requests to maintain GDPR compliance'
          });
          break;
        case 'EXPIRED_CONSENTS':
          recommendations.push({
            priority: 'MEDIUM',
            action: 'Refresh expired consent records',
            description: 'Contact users to renew consent for continued data processing'
          });
          break;
      }
    });

    // General recommendations
    recommendations.push({
      priority: 'LOW',
      action: 'Regular compliance audits',
      description: 'Conduct quarterly compliance reviews and update policies as needed'
    });

    return recommendations;
  }

  // Report data breach (GDPR Article 33)
  reportDataBreach(breachData) {
    const breachId = crypto.randomUUID();
    const breach = {
      id: breachId,
      detectedAt: new Date().toISOString(),
      reportedAt: new Date().toISOString(),
      type: breachData.type,
      severity: breachData.severity,
      affectedDataTypes: breachData.affectedDataTypes,
      affectedDataSubjects: breachData.affectedDataSubjects,
      cause: breachData.cause,
      containmentMeasures: breachData.containmentMeasures,
      riskAssessment: breachData.riskAssessment,
      notificationRequired: breachData.severity === 'HIGH' || breachData.affectedDataSubjects > 1000,
      authorityNotified: false,
      dataSubjectsNotified: false
    };

    this.breachNotifications.push(breach);

    // Log breach event
    this.logAuditEvent({
      action: 'DATA_BREACH_REPORTED',
      resource: 'data_breach',
      details: {
        breachId,
        type: breachData.type,
        severity: breachData.severity,
        affectedDataSubjects: breachData.affectedDataSubjects
      },
      riskLevel: breachData.severity,
      complianceFramework: ['GDPR']
    });

    return breach;
  }

  // Data retention policy management
  applyRetentionPolicy(dataType) {
    const policy = this.dataRetentionPolicies.get(dataType);
    
    if (!policy) {
      throw new Error(`No retention policy found for data type: ${dataType}`);
    }

    const now = Date.now();
    const retentionCutoff = now - policy.retentionPeriod;

    // In a real implementation, this would trigger data cleanup
    this.logAuditEvent({
      action: 'RETENTION_POLICY_APPLIED',
      resource: 'data_retention',
      details: {
        dataType,
        policyId: policy.id,
        retentionPeriod: policy.retentionPeriod,
        cutoffDate: new Date(retentionCutoff).toISOString()
      },
      complianceFramework: ['GDPR']
    });

    return {
      policyApplied: policy,
      cutoffDate: new Date(retentionCutoff).toISOString(),
      dataMarkedForDeletion: true // Would return actual count in real implementation
    };
  }

  // Get compliance dashboard data
  getComplianceDashboard() {
    const now = Date.now();
    const last30Days = now - (30 * 24 * 60 * 60 * 1000);

    const recentAuditLogs = this.auditLogs.filter(log => 
      new Date(log.timestamp).getTime() > last30Days
    );

    return {
      summary: {
        auditEvents: recentAuditLogs.length,
        dataSubjectRequests: recentAuditLogs.filter(log => 
          log.action.includes('DATA_ACCESS_REQUEST') || log.action.includes('DATA_DELETION_REQUEST')
        ).length,
        consentRecords: this.consentRecords.size,
        activeRetentionPolicies: this.dataRetentionPolicies.size,
        complianceScore: this.calculateGDPRComplianceScore()
      },
      frameworks: Object.keys(this.complianceFrameworks),
      recentActivity: recentAuditLogs.slice(-10),
      pendingActions: this.identifyComplianceIssues(),
      nextActions: [
        'Review and update privacy policy',
        'Conduct quarterly compliance audit',
        'Validate data retention policies'
      ]
    };
  }

  // Helper methods for calculations
  calculateAverageRequestTime(requests) {
    // Simplified calculation - would be more complex in real implementation
    return '5 days';
  }

  calculateConsentRate(events) {
    const given = events.filter(e => e.action === 'CONSENT_GIVEN').length;
    const total = events.length;
    return total > 0 ? Math.round((given / total) * 100) : 0;
  }

  calculateBreachComplianceRate(breaches) {
    const compliant = breaches.filter(b => b.authorityNotified).length;
    return breaches.length > 0 ? Math.round((compliant / breaches.length) * 100) : 100;
  }

  assessDataMinimization() {
    // Simplified assessment
    return 85; // Would be calculated based on actual data usage patterns
  }

  assessRetentionCompliance() {
    return {
      compliantPolicies: this.dataRetentionPolicies.size,
      totalPolicies: this.dataRetentionPolicies.size,
      complianceRate: 100
    };
  }

  generateSOXReport(auditLogs, options) {
    // Simplified SOX compliance report
    return {
      framework: 'SOX',
      summary: 'SOX compliance report - simplified implementation',
      auditEvents: auditLogs.length
    };
  }

  generatePCIReport(auditLogs, options) {
    // Simplified PCI DSS compliance report
    return {
      framework: 'PCI_DSS',
      summary: 'PCI DSS compliance report - simplified implementation',
      auditEvents: auditLogs.length
    };
  }

  generateGenericComplianceReport(framework, auditLogs, options) {
    return {
      framework,
      summary: `${framework} compliance report`,
      auditEvents: auditLogs.length,
      period: options
    };
  }
}

module.exports = ComplianceService;