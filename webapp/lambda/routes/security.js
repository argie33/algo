/**
 * Security Management Routes
 * Security dashboard, event monitoring, and threat management
 */

const express = require('express');
const { success, error } = require('../utils/responseFormatter');

const router = express.Router();

/**
 * GET /api/security/dashboard
 * Security dashboard with real-time threat monitoring
 */
router.get('/dashboard', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🛡️ [${diagnosticId}] Security dashboard requested...`);
    
    try {
        // Get security service instance (lazy loaded from main app)
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId,
                message: 'Security monitoring service is not initialized'
            }));
        }

        const dashboard = securityService.getSecurityDashboard();
        
        console.log(`🛡️ [${diagnosticId}] Security dashboard generated: ${dashboard.threatLevel} threat level`);
        
        res.json(success({
            ...dashboard,
            diagnosticId,
            message: 'Security dashboard retrieved successfully'
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security dashboard failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'security-dashboard' }));
    }
});

/**
 * GET /api/security/metrics
 * Security metrics and statistics
 */
router.get('/metrics', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`📊 [${diagnosticId}] Security metrics requested...`);
    
    try {
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId,
                message: 'Security monitoring service is not initialized'
            }));
        }

        const metrics = securityService.getMetrics();
        
        console.log(`📊 [${diagnosticId}] Security metrics retrieved: ${metrics.recentEventCount} recent events`);
        
        res.json(success({
            ...metrics,
            diagnosticId,
            message: 'Security metrics retrieved successfully'
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security metrics failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'security-metrics' }));
    }
});

/**
 * GET /api/security/events
 * Security events with filtering and pagination
 */
router.get('/events', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`📋 [${diagnosticId}] Security events requested...`);
    
    try {
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId
            }));
        }

        // Parse query parameters
        const {
            startTime = Date.now() - (24 * 60 * 60 * 1000), // Last 24 hours default
            endTime = Date.now(),
            eventType,
            severity,
            sourceIP,
            limit = 100,
            offset = 0
        } = req.query;

        // Get all events in time range
        const allEvents = securityService.securityEvents.filter(event => {
            if (event.timestamp < parseInt(startTime) || event.timestamp > parseInt(endTime)) {
                return false;
            }
            if (eventType && event.eventType !== eventType) {
                return false;
            }
            if (severity && event.severity !== severity) {
                return false;
            }
            if (sourceIP && event.sourceIP !== sourceIP) {
                return false;
            }
            return true;
        });

        // Sort by timestamp (newest first)
        allEvents.sort((a, b) => b.timestamp - a.timestamp);

        // Apply pagination
        const paginatedEvents = allEvents.slice(parseInt(offset), parseInt(offset) + parseInt(limit));

        const response = {
            diagnosticId,
            timeRange: { startTime: parseInt(startTime), endTime: parseInt(endTime) },
            filters: { eventType, severity, sourceIP },
            pagination: {
                total: allEvents.length,
                limit: parseInt(limit),
                offset: parseInt(offset),
                hasMore: parseInt(offset) + parseInt(limit) < allEvents.length
            },
            events: paginatedEvents.map(event => ({
                id: event.id,
                timestamp: event.timestamp,
                eventType: event.eventType,
                severity: event.severity,
                sourceIP: event.sourceIP,
                userAgent: event.userAgent,
                userId: event.userId,
                details: event.details
            }))
        };

        console.log(`📋 [${diagnosticId}] Security events retrieved: ${paginatedEvents.length}/${allEvents.length} events`);
        
        res.json(success(response));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security events failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'security-events' }));
    }
});

/**
 * POST /api/security/event
 * Log a security event
 */
router.post('/event', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`📝 [${diagnosticId}] Security event logging requested...`);
    
    try {
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId
            }));
        }

        const { eventType, severity, details } = req.body;

        // Validate required fields
        if (!eventType || !severity) {
            return res.json(error('Missing required fields: eventType, severity', {
                diagnosticId,
                provided: { eventType: !!eventType, severity: !!severity }
            }));
        }

        // Validate severity
        if (!['info', 'warning', 'critical'].includes(severity)) {
            return res.json(error('Invalid severity level', {
                diagnosticId,
                validSeverities: ['info', 'warning', 'critical'],
                provided: severity
            }));
        }

        const eventId = securityService.logSecurityEvent(eventType, severity, details, req);
        
        console.log(`📝 [${diagnosticId}] Security event logged: ${eventId}`);
        
        res.json(success({
            eventId,
            diagnosticId,
            message: 'Security event logged successfully'
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security event logging failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'log-security-event' }));
    }
});

/**
 * GET /api/security/export
 * Export security events for analysis
 */
router.get('/export', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`📤 [${diagnosticId}] Security events export requested...`);
    
    try {
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId
            }));
        }

        const {
            startTime = Date.now() - (7 * 24 * 60 * 60 * 1000), // Last 7 days default
            endTime = Date.now(),
            format = 'json'
        } = req.query;

        if (!['json', 'csv'].includes(format)) {
            return res.json(error('Invalid export format', {
                diagnosticId,
                validFormats: ['json', 'csv'],
                provided: format
            }));
        }

        const exportData = securityService.exportSecurityEvents(
            parseInt(startTime),
            parseInt(endTime),
            format
        );

        if (format === 'csv') {
            res.setHeader('Content-Type', 'text/csv');
            res.setHeader('Content-Disposition', `attachment; filename="security-events-${Date.now()}.csv"`);
            res.send(exportData);
        } else {
            res.json(success({
                ...exportData,
                diagnosticId,
                message: 'Security events exported successfully'
            }));
        }
        
        console.log(`📤 [${diagnosticId}] Security events exported: ${format} format`);
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security events export failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'export-security-events' }));
    }
});

/**
 * DELETE /api/security/events/cleanup
 * Clean up old security events
 */
router.delete('/events/cleanup', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🧹 [${diagnosticId}] Security events cleanup requested...`);
    
    try {
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId
            }));
        }

        const { olderThan = 7 * 24 * 60 * 60 * 1000 } = req.body; // 7 days default

        const removedCount = securityService.clearOldEvents(parseInt(olderThan));
        
        console.log(`🧹 [${diagnosticId}] Security events cleanup completed: ${removedCount} events removed`);
        
        res.json(success({
            removedCount,
            olderThan: parseInt(olderThan),
            diagnosticId,
            message: `Cleaned up ${removedCount} old security events`
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security events cleanup failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'cleanup-security-events' }));
    }
});

/**
 * GET /api/security/threat-level
 * Current threat level assessment
 */
router.get('/threat-level', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🎯 [${diagnosticId}] Threat level assessment requested...`);
    
    try {
        const securityService = req.app.locals.securityService;
        
        if (!securityService) {
            return res.json(error('Security service not available', {
                diagnosticId
            }));
        }

        const currentTime = Date.now();
        const lastHour = currentTime - (60 * 60 * 1000);
        
        const recentEvents = securityService.securityEvents.filter(
            event => event.timestamp > lastHour
        );

        const threatAssessment = {
            currentLevel: securityService.threatLevel,
            lastAssessment: securityService.metrics.lastThreatAssessment,
            recentActivity: {
                totalEvents: recentEvents.length,
                criticalEvents: recentEvents.filter(e => e.severity === 'critical').length,
                warningEvents: recentEvents.filter(e => e.severity === 'warning').length,
                uniqueIPs: new Set(recentEvents.map(e => e.sourceIP)).size
            },
            trends: {
                increasing: recentEvents.length > 20,
                stable: recentEvents.length >= 5 && recentEvents.length <= 20,
                decreasing: recentEvents.length < 5
            }
        };

        console.log(`🎯 [${diagnosticId}] Threat level assessment: ${threatAssessment.currentLevel}`);
        
        res.json(success({
            ...threatAssessment,
            diagnosticId,
            message: 'Threat level assessment retrieved successfully'
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Threat level assessment failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'threat-level-assessment' }));
    }
});

/**
 * GET /api/security/status
 * Overall security system status
 */
router.get('/status', async (req, res) => {
    const diagnosticId = Math.random().toString(36).substr(2, 9);
    
    console.log(`🔍 [${diagnosticId}] Security system status requested...`);
    
    try {
        // Check for security middleware availability
        const securityService = req.app.locals.securityService;
        const rateLimitingMiddleware = req.app.locals.rateLimitingMiddleware;
        const authMiddleware = req.app.locals.authMiddleware;

        const status = {
            timestamp: Date.now(),
            diagnosticId,
            services: {
                securityService: {
                    status: securityService ? 'active' : 'inactive',
                    threatLevel: securityService?.threatLevel || 'unknown',
                    eventCount: securityService?.securityEvents?.length || 0
                },
                rateLimiting: {
                    status: rateLimitingMiddleware ? 'active' : 'inactive',
                    stats: rateLimitingMiddleware?.getStats() || null
                },
                authentication: {
                    status: authMiddleware ? 'active' : 'inactive',
                    stats: authMiddleware?.getStats() || null
                }
            },
            overall: 'unknown'
        };

        // Calculate overall status
        const activeServices = Object.values(status.services).filter(s => s.status === 'active').length;
        const totalServices = Object.keys(status.services).length;
        
        if (activeServices === totalServices) {
            status.overall = 'healthy';
        } else if (activeServices > totalServices / 2) {
            status.overall = 'degraded';
        } else {
            status.overall = 'critical';
        }

        console.log(`🔍 [${diagnosticId}] Security system status: ${status.overall}`);
        
        res.json(success({
            ...status,
            message: 'Security system status retrieved successfully'
        }));
        
    } catch (error) {
        console.error(`❌ [${diagnosticId}] Security system status failed:`, error.message);
        res.json(error(error.message, { diagnosticId, operation: 'security-system-status' }));
    }
});

module.exports = router;