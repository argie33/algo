/**
 * Notification Service
 * Comprehensive real-time notification system for trading platform
 * Integrates with multiple notification channels and replaces mock notifications
 */

const { query, transaction } = require('../utils/database');
const PortfolioAlerts = require('../utils/portfolioAlerts');
const WatchlistAlerts = require('../utils/watchlistAlerts');
const logger = require('../utils/logger');

class NotificationService {
    constructor() {
        this.portfolioAlerts = new PortfolioAlerts();
        
        // Initialize watchlist alerts if available
        try {
            this.watchlistAlerts = new WatchlistAlerts();
        } catch (error) {
            console.warn('⚠️ Watchlist alerts not available:', error.message);
            this.watchlistAlerts = null;
        }
        
        // Notification types
        this.notificationTypes = {
            PRICE_ALERT: 'price_alert',
            VOLUME_ALERT: 'volume_alert',
            TECHNICAL_ALERT: 'technical_alert',
            PORTFOLIO_ALERT: 'portfolio_alert',
            EARNINGS_ALERT: 'earnings_alert',
            NEWS_ALERT: 'news_alert',
            STRATEGY_ALERT: 'strategy_alert',
            SYSTEM_ALERT: 'system_alert'
        };
        
        // Priority levels
        this.priorities = {
            LOW: 'low',
            MEDIUM: 'medium',
            HIGH: 'high',
            CRITICAL: 'critical'
        };
        
        // Notification channels
        this.channels = {
            IN_APP: 'in_app',
            EMAIL: 'email',
            SMS: 'sms',
            PUSH: 'push'
        };
        
        console.log('📢 Notification Service initialized');
    }

    /**
     * Create a new notification
     */
    async createNotification(userId, notificationData) {
        try {
            const {
                type,
                title,
                message,
                priority = this.priorities.MEDIUM,
                category = 'general',
                metadata = {},
                channels = [this.channels.IN_APP],
                expiresAt = null,
                actionUrl = null
            } = notificationData;

            logger.info('📢 Creating notification', {
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
                type,
                priority,
                channels: channels.length
            });

            // Validate required fields
            if (!type || !title || !message) {
                throw new Error('Missing required notification fields: type, title, message');
            }

            if (!Object.values(this.notificationTypes).includes(type)) {
                throw new Error(`Invalid notification type: ${type}`);
            }

            if (!Object.values(this.priorities).includes(priority)) {
                throw new Error(`Invalid notification priority: ${priority}`);
            }

            // Insert notification into database
            const result = await query(`
                INSERT INTO alert_notifications (
                    user_id, type, title, message, priority, category, 
                    metadata, channels, expires_at, action_url, 
                    created_at, read_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW(), NULL)
                RETURNING *
            `, [
                userId, type, title, message, priority, category,
                JSON.stringify(metadata), JSON.stringify(channels),
                expiresAt, actionUrl
            ]);

            const notification = result.rows[0];

            // Process notification channels
            await this.processNotificationChannels(notification);

            logger.info('✅ Notification created successfully', {
                notificationId: notification.id,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
                type,
                channels: channels.length
            });

            return this.formatNotification(notification);
        } catch (error) {
            logger.error('❌ Error creating notification', {
                error: error.message,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
                type: notificationData.type
            });
            throw error;
        }
    }

    /**
     * Get user notifications with filtering and pagination
     */
    async getUserNotifications(userId, options = {}) {
        try {
            const {
                limit = 50,
                offset = 0,
                unreadOnly = false,
                type = null,
                priority = null,
                category = null
            } = options;

            logger.info('📋 Fetching user notifications', {
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
                limit,
                unreadOnly,
                hasFilters: !!(type || priority || category)
            });

            // Build WHERE clause
            let whereClause = 'WHERE user_id = $1';
            const params = [userId];
            let paramIndex = 2;

            if (unreadOnly) {
                whereClause += ' AND read_at IS NULL';
            }

            if (type) {
                whereClause += ` AND type = $${paramIndex}`;
                params.push(type);
                paramIndex++;
            }

            if (priority) {
                whereClause += ` AND priority = $${paramIndex}`;
                params.push(priority);
                paramIndex++;
            }

            if (category) {
                whereClause += ` AND category = $${paramIndex}`;
                params.push(category);
                paramIndex++;
            }

            // Add expiration filter
            whereClause += ' AND (expires_at IS NULL OR expires_at > NOW())';

            // Get notifications
            const result = await query(`
                SELECT 
                    id, user_id, type, title, message, priority, category,
                    metadata, channels, expires_at, action_url,
                    created_at, read_at, updated_at
                FROM alert_notifications
                ${whereClause}
                ORDER BY created_at DESC
                LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
            `, [...params, limit, offset]);

            // Get total count for pagination
            const countResult = await query(`
                SELECT COUNT(*) as total
                FROM alert_notifications
                ${whereClause}
            `, params);

            const notifications = result.rows.map(row => this.formatNotification(row));
            const totalCount = parseInt(countResult.rows[0].total);

            logger.info('✅ User notifications fetched', {
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
                count: notifications.length,
                totalCount
            });

            return {
                notifications,
                pagination: {
                    total: totalCount,
                    limit,
                    offset,
                    hasMore: offset + notifications.length < totalCount
                }
            };
        } catch (error) {
            logger.error('❌ Error fetching user notifications', {
                error: error.message,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Mark notification as read
     */
    async markAsRead(userId, notificationId) {
        try {
            logger.info('✅ Marking notification as read', {
                notificationId,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });

            const result = await query(`
                UPDATE alert_notifications 
                SET read_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND user_id = $2 AND read_at IS NULL
                RETURNING *
            `, [notificationId, userId]);

            if (result.rows.length === 0) {
                throw new Error('Notification not found or already read');
            }

            return this.formatNotification(result.rows[0]);
        } catch (error) {
            logger.error('❌ Error marking notification as read', {
                error: error.message,
                notificationId,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Mark multiple notifications as read
     */
    async markMultipleAsRead(userId, notificationIds) {
        try {
            if (!Array.isArray(notificationIds) || notificationIds.length === 0) {
                throw new Error('Invalid notification IDs array');
            }

            logger.info('✅ Marking multiple notifications as read', {
                count: notificationIds.length,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });

            const placeholders = notificationIds.map((_, index) => `$${index + 2}`).join(',');
            
            const result = await query(`
                UPDATE alert_notifications 
                SET read_at = NOW(), updated_at = NOW()
                WHERE user_id = $1 AND id IN (${placeholders}) AND read_at IS NULL
                RETURNING id
            `, [userId, ...notificationIds]);

            return { markedCount: result.rows.length };
        } catch (error) {
            logger.error('❌ Error marking multiple notifications as read', {
                error: error.message,
                count: notificationIds?.length || 0,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Delete notification
     */
    async deleteNotification(userId, notificationId) {
        try {
            logger.info('🗑️ Deleting notification', {
                notificationId,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });

            const result = await query(`
                DELETE FROM alert_notifications 
                WHERE id = $1 AND user_id = $2
                RETURNING id
            `, [notificationId, userId]);

            if (result.rows.length === 0) {
                throw new Error('Notification not found or access denied');
            }

            return { deleted: true, notificationId };
        } catch (error) {
            logger.error('❌ Error deleting notification', {
                error: error.message,
                notificationId,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Process portfolio alerts and create notifications
     */
    async processPortfolioNotifications(userId) {
        try {
            logger.info('📊 Processing portfolio notifications', {
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });

            const result = await this.portfolioAlerts.processUserPortfolioAlerts(userId);
            
            if (result.triggeredCount > 0) {
                logger.info('📢 Portfolio alerts triggered', {
                    userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
                    triggeredCount: result.triggeredCount
                });
            }

            return result;
        } catch (error) {
            logger.error('❌ Error processing portfolio notifications', {
                error: error.message,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Create price alert notification
     */
    async createPriceAlert(userId, symbol, currentPrice, targetPrice, condition) {
        try {
            const title = `Price Alert: ${symbol}`;
            const message = `${symbol} has ${condition} your target price of $${targetPrice.toFixed(2)}. Current price: $${currentPrice.toFixed(2)}`;
            
            return await this.createNotification(userId, {
                type: this.notificationTypes.PRICE_ALERT,
                title,
                message,
                priority: this.priorities.HIGH,
                category: 'trading',
                metadata: {
                    symbol,
                    currentPrice,
                    targetPrice,
                    condition,
                    priceChange: ((currentPrice - targetPrice) / targetPrice * 100).toFixed(2)
                },
                channels: [this.channels.IN_APP, this.channels.PUSH]
            });
        } catch (error) {
            logger.error('❌ Error creating price alert', {
                error: error.message,
                symbol,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Create volume spike alert
     */
    async createVolumeAlert(userId, symbol, currentVolume, averageVolume, percentIncrease) {
        try {
            const title = `Volume Alert: ${symbol}`;
            const message = `${symbol} is experiencing unusual volume. Current: ${this.formatNumber(currentVolume)}, Average: ${this.formatNumber(averageVolume)} (+${percentIncrease.toFixed(0)}%)`;
            
            return await this.createNotification(userId, {
                type: this.notificationTypes.VOLUME_ALERT,
                title,
                message,
                priority: this.priorities.MEDIUM,
                category: 'trading',
                metadata: {
                    symbol,
                    currentVolume,
                    averageVolume,
                    percentIncrease
                }
            });
        } catch (error) {
            logger.error('❌ Error creating volume alert', {
                error: error.message,
                symbol,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Create strategy execution notification
     */
    async createStrategyNotification(userId, strategyId, strategyName, executionResult) {
        try {
            const title = `Strategy Executed: ${strategyName}`;
            const message = executionResult.success 
                ? `Strategy executed successfully. ${executionResult.orders?.length || 0} orders placed.`
                : `Strategy execution failed: ${executionResult.error}`;
            
            return await this.createNotification(userId, {
                type: this.notificationTypes.STRATEGY_ALERT,
                title,
                message,
                priority: executionResult.success ? this.priorities.MEDIUM : this.priorities.HIGH,
                category: 'strategy',
                metadata: {
                    strategyId,
                    strategyName,
                    executionResult,
                    ordersCount: executionResult.orders?.length || 0
                }
            });
        } catch (error) {
            logger.error('❌ Error creating strategy notification', {
                error: error.message,
                strategyId,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            throw error;
        }
    }

    /**
     * Get unread notification count
     */
    async getUnreadCount(userId) {
        try {
            const result = await query(`
                SELECT COUNT(*) as count
                FROM alert_notifications
                WHERE user_id = $1 
                  AND read_at IS NULL 
                  AND (expires_at IS NULL OR expires_at > NOW())
            `, [userId]);

            return parseInt(result.rows[0].count);
        } catch (error) {
            logger.error('❌ Error getting unread count', {
                error: error.message,
                userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
            });
            return 0;
        }
    }

    /**
     * Process notification channels (email, SMS, push, etc.)
     */
    async processNotificationChannels(notification) {
        try {
            const channels = Array.isArray(notification.channels) 
                ? notification.channels 
                : JSON.parse(notification.channels || '["in_app"]');

            for (const channel of channels) {
                try {
                    switch (channel) {
                        case this.channels.EMAIL:
                            await this.sendEmailNotification(notification);
                            break;
                        case this.channels.SMS:
                            await this.sendSmsNotification(notification);
                            break;
                        case this.channels.PUSH:
                            await this.sendPushNotification(notification);
                            break;
                        case this.channels.IN_APP:
                        default:
                            // In-app notifications are handled by database storage
                            break;
                    }
                } catch (channelError) {
                    logger.warn('⚠️ Failed to process notification channel', {
                        channel,
                        notificationId: notification.id,
                        error: channelError.message
                    });
                }
            }
        } catch (error) {
            logger.error('❌ Error processing notification channels', {
                error: error.message,
                notificationId: notification.id
            });
        }
    }

    /**
     * Send email notification (placeholder for real email service integration)
     */
    async sendEmailNotification(notification) {
        // This would integrate with AWS SES, SendGrid, or similar service
        logger.info('📧 Email notification queued', {
            notificationId: notification.id,
            userId: notification.user_id ? `${notification.user_id.substring(0, 8)}...` : 'unknown'
        });
        
        // TODO: Integrate with real email service
        // await emailService.send({
        //     to: userEmail,
        //     subject: notification.title,
        //     body: notification.message
        // });
    }

    /**
     * Send SMS notification (placeholder for real SMS service integration)
     */
    async sendSmsNotification(notification) {
        // This would integrate with AWS SNS, Twilio, or similar service
        logger.info('📱 SMS notification queued', {
            notificationId: notification.id,
            userId: notification.user_id ? `${notification.user_id.substring(0, 8)}...` : 'unknown'
        });
        
        // TODO: Integrate with real SMS service
        // await smsService.send({
        //     to: userPhoneNumber,
        //     message: notification.message
        // });
    }

    /**
     * Send push notification (placeholder for real push service integration)
     */
    async sendPushNotification(notification) {
        // This would integrate with Firebase FCM, Apple Push, or similar service
        logger.info('🔔 Push notification queued', {
            notificationId: notification.id,
            userId: notification.user_id ? `${notification.user_id.substring(0, 8)}...` : 'unknown'
        });
        
        // TODO: Integrate with real push service
        // await pushService.send({
        //     deviceTokens: userDeviceTokens,
        //     title: notification.title,
        //     body: notification.message
        // });
    }

    /**
     * Format notification for API response
     */
    formatNotification(row) {
        return {
            id: row.id,
            type: row.type,
            title: row.title,
            message: row.message,
            priority: row.priority,
            category: row.category,
            metadata: typeof row.metadata === 'string' ? JSON.parse(row.metadata) : row.metadata,
            channels: typeof row.channels === 'string' ? JSON.parse(row.channels) : row.channels,
            isRead: !!row.read_at,
            readAt: row.read_at,
            createdAt: row.created_at,
            updatedAt: row.updated_at,
            expiresAt: row.expires_at,
            actionUrl: row.action_url
        };
    }

    /**
     * Format large numbers for display
     */
    formatNumber(num) {
        if (num >= 1000000) {
            return (num / 1000000).toFixed(1) + 'M';
        } else if (num >= 1000) {
            return (num / 1000).toFixed(1) + 'K';
        }
        return num.toString();
    }

    /**
     * Clean up expired notifications
     */
    async cleanupExpiredNotifications() {
        try {
            const result = await query(`
                DELETE FROM alert_notifications 
                WHERE expires_at IS NOT NULL AND expires_at < NOW()
                RETURNING COUNT(*) as deleted_count
            `);

            const deletedCount = result.rows[0]?.deleted_count || 0;
            
            if (deletedCount > 0) {
                logger.info('🧹 Cleaned up expired notifications', {
                    deletedCount
                });
            }

            return deletedCount;
        } catch (error) {
            logger.error('❌ Error cleaning up expired notifications', {
                error: error.message
            });
            return 0;
        }
    }
}

module.exports = NotificationService;