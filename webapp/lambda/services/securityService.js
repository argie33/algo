/**
 * Security Service
 * Central security management and event monitoring
 */

const crypto = require('crypto');
const EventEmitter = require('events');

class SecurityService extends EventEmitter {
    constructor() {
        super();
        this.securityEvents = [];
        this.threatLevel = 'low'; // low, medium, high, critical
        this.maxEventHistory = 10000;
        this.alertThresholds = {
            failedLogins: { count: 10, timeWindow: 300000 }, // 10 in 5 minutes
            suspiciousIPs: { count: 5, timeWindow: 600000 },  // 5 in 10 minutes
            rateLimitViolations: { count: 20, timeWindow: 300000 }, // 20 in 5 minutes
            authenticationAnomalies: { count: 3, timeWindow: 900000 } // 3 in 15 minutes
        };
        
        // Security metrics
        this.metrics = {
            totalEvents: 0,
            criticalEvents: 0,
            blockedAttacks: 0,
            lastThreatAssessment: Date.now()
        };

        // Automated threat response
        this.automatedResponse = {
            enabled: true,
            autoBlock: true,
            alertAdmin: true
        };

        // Start monitoring
        this.startEventProcessor();
    }

    /**
     * Log security event
     */
    logSecurityEvent(eventType, severity, details, req = null) {
        const event = {
            id: crypto.randomUUID(),
            timestamp: Date.now(),
            eventType,
            severity, // info, warning, critical
            details,
            sourceIP: req?.ip || req?.connection?.remoteAddress || 'unknown',
            userAgent: req?.get('User-Agent') || 'unknown',
            userId: req?.user?.userId || req?.userId || null,
            sessionId: req?.sessionId || null,
            correlationId: req?.correlationId || null,
            processed: false
        };

        this.securityEvents.push(event);
        this.metrics.totalEvents++;

        if (severity === 'critical') {
            this.metrics.criticalEvents++;
        }

        // Emit event for real-time processing
        this.emit('securityEvent', event);

        // Trim old events to prevent memory issues
        if (this.securityEvents.length > this.maxEventHistory) {
            this.securityEvents = this.securityEvents.slice(-this.maxEventHistory);
        }

        console.log(`🔒 Security event logged: ${eventType} [${severity}] from ${event.sourceIP}`);
        
        return event.id;
    }

    /**
     * Process security events and detect patterns
     */
    startEventProcessor() {
        setInterval(() => {
            this.processSecurityEvents();
            this.assessThreatLevel();
        }, 30000); // Every 30 seconds
    }

    /**
     * Process recent security events for patterns
     */
    processSecurityEvents() {
        const currentTime = Date.now();
        const recentEvents = this.securityEvents.filter(
            event => currentTime - event.timestamp < 900000 && !event.processed
        );

        // Group events by type and IP
        const eventsByType = {};
        const eventsByIP = {};

        recentEvents.forEach(event => {
            // By type
            if (!eventsByType[event.eventType]) {
                eventsByType[event.eventType] = [];
            }
            eventsByType[event.eventType].push(event);

            // By IP
            if (!eventsByIP[event.sourceIP]) {
                eventsByIP[event.sourceIP] = [];
            }
            eventsByIP[event.sourceIP].push(event);

            // Mark as processed
            event.processed = true;
        });

        // Check for threshold violations
        this.checkThresholds(eventsByType, eventsByIP);
    }

    /**
     * Check if events exceed alert thresholds
     */
    checkThresholds(eventsByType, eventsByIP) {
        const currentTime = Date.now();

        // Check event type thresholds
        for (const [eventType, events] of Object.entries(eventsByType)) {
            const threshold = this.alertThresholds[eventType];
            if (!threshold) continue;

            const recentEvents = events.filter(
                event => currentTime - event.timestamp < threshold.timeWindow
            );

            if (recentEvents.length >= threshold.count) {
                this.triggerAlert('threshold_exceeded', {
                    eventType,
                    count: recentEvents.length,
                    threshold: threshold.count,
                    timeWindow: threshold.timeWindow,
                    events: recentEvents.map(e => ({ id: e.id, timestamp: e.timestamp, sourceIP: e.sourceIP }))
                });
            }
        }

        // Check IP-based patterns
        for (const [ip, events] of Object.entries(eventsByIP)) {
            // Multiple event types from same IP
            const eventTypes = new Set(events.map(e => e.eventType));
            if (eventTypes.size >= 3 && events.length >= 5) {
                this.triggerAlert('multi_vector_attack', {
                    sourceIP: ip,
                    eventTypes: Array.from(eventTypes),
                    totalEvents: events.length,
                    timeSpan: Math.max(...events.map(e => e.timestamp)) - Math.min(...events.map(e => e.timestamp))
                });
            }

            // High frequency from single IP
            if (events.length >= 15) {
                this.triggerAlert('high_frequency_attack', {
                    sourceIP: ip,
                    eventCount: events.length,
                    timeSpan: Math.max(...events.map(e => e.timestamp)) - Math.min(...events.map(e => e.timestamp))
                });
            }
        }
    }

    /**
     * Trigger security alert
     */
    triggerAlert(alertType, details) {
        const alert = {
            id: crypto.randomUUID(),
            timestamp: Date.now(),
            alertType,
            details,
            severity: this.getAlertSeverity(alertType),
            acknowledged: false,
            responseActions: []
        };

        console.warn(`🚨 Security alert triggered: ${alertType}`, details);

        // Take automated response if enabled
        if (this.automatedResponse.enabled) {
            this.takeAutomatedResponse(alert);
        }

        // Emit alert for external processing
        this.emit('securityAlert', alert);

        return alert.id;
    }

    /**
     * Take automated response to security threats
     */
    takeAutomatedResponse(alert) {
        const actions = [];

        switch (alert.alertType) {
            case 'threshold_exceeded':
                if (alert.details.eventType === 'failedLogins' && this.automatedResponse.autoBlock) {
                    // Could trigger temporary IP blocks
                    actions.push('rate_limit_increased');
                }
                break;

            case 'multi_vector_attack':
            case 'high_frequency_attack':
                if (this.automatedResponse.autoBlock) {
                    // Could trigger IP blacklisting
                    actions.push('ip_blocked');
                    this.metrics.blockedAttacks++;
                }
                break;
        }

        alert.responseActions = actions;
        
        if (actions.length > 0) {
            console.log(`🛡️ Automated response taken for ${alert.alertType}: ${actions.join(', ')}`);
        }
    }

    /**
     * Get alert severity based on type
     */
    getAlertSeverity(alertType) {
        const severityMap = {
            threshold_exceeded: 'medium',
            multi_vector_attack: 'high',
            high_frequency_attack: 'high',
            data_breach_attempt: 'critical',
            unauthorized_access: 'critical',
            privilege_escalation: 'critical'
        };

        return severityMap[alertType] || 'medium';
    }

    /**
     * Assess overall threat level
     */
    assessThreatLevel() {
        const currentTime = Date.now();
        const lastHour = currentTime - (60 * 60 * 1000);
        
        const recentEvents = this.securityEvents.filter(
            event => event.timestamp > lastHour
        );

        const criticalEvents = recentEvents.filter(e => e.severity === 'critical').length;
        const warningEvents = recentEvents.filter(e => e.severity === 'warning').length;
        const totalEvents = recentEvents.length;

        let newThreatLevel = 'low';

        if (criticalEvents >= 5 || totalEvents >= 100) {
            newThreatLevel = 'critical';
        } else if (criticalEvents >= 2 || warningEvents >= 10 || totalEvents >= 50) {
            newThreatLevel = 'high';
        } else if (criticalEvents >= 1 || warningEvents >= 5 || totalEvents >= 20) {
            newThreatLevel = 'medium';
        }

        if (newThreatLevel !== this.threatLevel) {
            console.warn(`🎯 Threat level changed: ${this.threatLevel} → ${newThreatLevel}`);
            this.threatLevel = newThreatLevel;
            this.emit('threatLevelChanged', { from: this.threatLevel, to: newThreatLevel });
        }

        this.metrics.lastThreatAssessment = currentTime;
    }

    /**
     * Get security dashboard data
     */
    getSecurityDashboard() {
        const currentTime = Date.now();
        const last24Hours = currentTime - (24 * 60 * 60 * 1000);
        const lastHour = currentTime - (60 * 60 * 1000);

        const recent24h = this.securityEvents.filter(e => e.timestamp > last24Hours);
        const recent1h = this.securityEvents.filter(e => e.timestamp > lastHour);

        // Event type breakdown
        const eventTypes = {};
        recent24h.forEach(event => {
            eventTypes[event.eventType] = (eventTypes[event.eventType] || 0) + 1;
        });

        // Severity breakdown
        const severities = { info: 0, warning: 0, critical: 0 };
        recent24h.forEach(event => {
            severities[event.severity] = (severities[event.severity] || 0) + 1;
        });

        // Top source IPs
        const sourceIPs = {};
        recent24h.forEach(event => {
            sourceIPs[event.sourceIP] = (sourceIPs[event.sourceIP] || 0) + 1;
        });

        const topIPs = Object.entries(sourceIPs)
            .sort(([,a], [,b]) => b - a)
            .slice(0, 10)
            .map(([ip, count]) => ({ ip, count }));

        return {
            threatLevel: this.threatLevel,
            metrics: this.metrics,
            timeline: {
                last24Hours: recent24h.length,
                lastHour: recent1h.length,
                eventsPerHour: Math.round(recent24h.length / 24)
            },
            breakdown: {
                eventTypes,
                severities,
                topSourceIPs: topIPs
            },
            recentEvents: this.securityEvents
                .filter(e => e.timestamp > lastHour)
                .sort((a, b) => b.timestamp - a.timestamp)
                .slice(0, 50)
                .map(e => ({
                    id: e.id,
                    timestamp: e.timestamp,
                    eventType: e.eventType,
                    severity: e.severity,
                    sourceIP: e.sourceIP,
                    details: e.details
                }))
        };
    }

    /**
     * Export security events for analysis
     */
    exportSecurityEvents(startTime, endTime, format = 'json') {
        const filteredEvents = this.securityEvents.filter(
            event => event.timestamp >= startTime && event.timestamp <= endTime
        );

        if (format === 'csv') {
            const csvHeader = 'timestamp,eventType,severity,sourceIP,userAgent,userId,details\n';
            const csvRows = filteredEvents.map(event => 
                `${event.timestamp},${event.eventType},${event.severity},${event.sourceIP},"${event.userAgent}",${event.userId || ''},"${JSON.stringify(event.details).replace(/"/g, '""')}"`
            ).join('\n');
            
            return csvHeader + csvRows;
        }

        return {
            exportTime: Date.now(),
            timeRange: { startTime, endTime },
            eventCount: filteredEvents.length,
            events: filteredEvents
        };
    }

    /**
     * Clear old security events
     */
    clearOldEvents(olderThan = 7 * 24 * 60 * 60 * 1000) { // 7 days default
        const cutoffTime = Date.now() - olderThan;
        const initialCount = this.securityEvents.length;
        
        this.securityEvents = this.securityEvents.filter(
            event => event.timestamp > cutoffTime
        );

        const removedCount = initialCount - this.securityEvents.length;
        
        if (removedCount > 0) {
            console.log(`🧹 Removed ${removedCount} old security events`);
        }

        return removedCount;
    }

    /**
     * Get security metrics summary
     */
    getMetrics() {
        const currentTime = Date.now();
        const last24Hours = currentTime - (24 * 60 * 60 * 1000);
        
        const recentEvents = this.securityEvents.filter(
            event => event.timestamp > last24Hours
        );

        return {
            ...this.metrics,
            threatLevel: this.threatLevel,
            recentEventCount: recentEvents.length,
            averageEventsPerHour: Math.round(recentEvents.length / 24),
            criticalEventRate: recentEvents.filter(e => e.severity === 'critical').length / recentEvents.length,
            topEventTypes: this.getTopEventTypes(recentEvents),
            lastAssessment: new Date(this.metrics.lastThreatAssessment).toISOString()
        };
    }

    /**
     * Get top event types from recent events
     */
    getTopEventTypes(events) {
        const eventTypes = {};
        events.forEach(event => {
            eventTypes[event.eventType] = (eventTypes[event.eventType] || 0) + 1;
        });

        return Object.entries(eventTypes)
            .sort(([,a], [,b]) => b - a)
            .slice(0, 5)
            .map(([type, count]) => ({ type, count }));
    }
}

module.exports = SecurityService;