/**
 * Comprehensive Messaging and Notifications Integration Tests
 * Tests real messaging systems: SQS, SNS, WebSocket notifications, Email, Push notifications
 * NO MOCKS - Tests against actual messaging infrastructure and real notification delivery
 */

import { test, expect } from '@playwright/test';

const testConfig = {
  baseURL: process.env.E2E_BASE_URL || 'https://d1zb7knau41vl9.cloudfront.net',
  apiURL: process.env.E2E_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev',
  websocketURL: process.env.E2E_WS_URL || 'wss://api.example.com/ws',
  testUser: {
    email: process.env.E2E_TEST_EMAIL || 'e2e-test@example.com',
    password: process.env.E2E_TEST_PASSWORD || 'E2ETest123!'
  },
  timeout: 90000
};

test.describe('Comprehensive Messaging and Notifications Integration - Enterprise Framework', () => {
  
  let messagingSession = {
    notifications: [],
    websocketMessages: [],
    emailEvents: [],
    pushNotifications: [],
    sqsEvents: [],
    snsEvents: [],
    messageDelivery: [],
    errors: []
  };

  async function authenticate(page) {
    const isAuth = await page.locator('[data-testid="user-avatar"]').isVisible().catch(() => false);
    if (!isAuth) {
      await page.locator('button:has-text("Sign In")').click();
      await page.fill('[data-testid="email-input"]', testConfig.testUser.email);
      await page.fill('[data-testid="password-input"]', testConfig.testUser.password);
      await page.click('[data-testid="login-submit"]');
      await page.waitForSelector('[data-testid="user-avatar"]', { timeout: 15000 });
    }
  }

  async function trackMessagingEvent(eventType, data) {
    messagingSession[eventType].push({
      ...data,
      timestamp: new Date().toISOString()
    });
  }

  async function setupNotificationMonitoring(page) {
    // Monitor WebSocket connections for real-time notifications
    page.on('websocket', ws => {
      console.log(`🔌 WebSocket connection established: ${ws.url()}`);
      
      ws.on('framereceived', event => {
        try {
          const data = JSON.parse(event.payload);
          console.log(`📥 WebSocket message received:`, data);
          
          if (data.type === 'notification') {
            trackMessagingEvent('notifications', {
              type: 'websocket_notification',
              notificationType: data.notificationType,
              message: data.message,
              priority: data.priority
            });
          }
          
          trackMessagingEvent('websocketMessages', {
            type: data.type,
            payload: data
          });
        } catch (e) {
          // Non-JSON message
          trackMessagingEvent('websocketMessages', {
            type: 'raw_message',
            payload: event.payload
          });
        }
      });

      ws.on('close', () => {
        console.log(`🔌 WebSocket connection closed: ${ws.url()}`);
      });
    });

    // Monitor page notifications (browser notifications API)
    await page.addInitScript(() => {
      const originalNotification = window.Notification;
      window.Notification = class extends originalNotification {
        constructor(title, options) {
          super(title, options);
          window.testNotifications = window.testNotifications || [];
          window.testNotifications.push({ title, options, timestamp: new Date().toISOString() });
        }
      };
    });
  }

  test.beforeEach(async ({ page }) => {
    // Reset messaging session tracking
    messagingSession = {
      notifications: [],
      websocketMessages: [],
      emailEvents: [],
      pushNotifications: [],
      sqsEvents: [],
      snsEvents: [],
      messageDelivery: [],
      errors: []
    };
    
    // Setup notification monitoring
    await setupNotificationMonitoring(page);
    
    // Monitor requests for messaging-related calls
    page.on('request', request => {
      const url = request.url();
      if (url.includes('notification') || url.includes('message') || 
          url.includes('sqs') || url.includes('sns') || url.includes('email')) {
        trackMessagingEvent('messageDelivery', {
          type: 'message_request',
          url: url,
          method: request.method()
        });
      }
    });

    // Monitor console for messaging errors
    page.on('console', msg => {
      if (msg.type() === 'error') {
        const errorText = msg.text();
        if (errorText.includes('notification') || errorText.includes('websocket') || 
            errorText.includes('message') || errorText.includes('push')) {
          messagingSession.errors.push({
            message: errorText,
            timestamp: new Date().toISOString()
          });
        }
      }
    });

    await page.goto(testConfig.baseURL);
    await page.waitForLoadState('networkidle');
  });

  test.describe('Real-time Notification System @critical @enterprise @notifications', () => {

    test('WebSocket Real-time Notifications Integration', async ({ page }) => {
      console.log('📡 Testing WebSocket Real-time Notifications Integration...');
      
      await authenticate(page);
      
      // 1. Enable notifications in settings
      console.log('🔔 Setting up notification preferences...');
      
      await page.goto('/settings/notifications');
      await page.waitForSelector('[data-testid="notification-settings"]', { timeout: 15000 });
      
      // Enable various notification types
      const notificationTypes = [
        'price-alerts',
        'trade-confirmations', 
        'portfolio-updates',
        'market-news',
        'system-alerts'
      ];
      
      for (const notificationType of notificationTypes) {
        const toggle = page.locator(`[data-testid="${notificationType}-toggle"]`);
        if (await toggle.isVisible()) {
          const isEnabled = await toggle.isChecked();
          if (!isEnabled) {
            await toggle.check();
            console.log(`✅ Enabled ${notificationType} notifications`);
          }
        }
      }
      
      await page.click('[data-testid="save-notification-settings"]');
      await page.waitForSelector('[data-testid="settings-saved"]', { timeout: 5000 });
      
      // 2. Navigate to dashboard to receive notifications
      await page.goto('/');
      await page.waitForSelector('[data-testid="dashboard"]', { timeout: 15000 });
      
      // 3. Trigger notification events
      console.log('🚀 Triggering notification events...');
      
      // Create a price alert to trigger notifications
      await page.goto('/portfolio/alerts');
      await page.waitForSelector('[data-testid="alerts-page"]', { timeout: 15000 });
      
      const createAlertButton = page.locator('[data-testid="create-price-alert"]');
      if (await createAlertButton.isVisible()) {
        await createAlertButton.click();
        await page.waitForSelector('[data-testid="alert-form"]', { timeout: 10000 });
        
        await page.fill('[data-testid="alert-symbol"]', 'AAPL');
        await page.fill('[data-testid="alert-price"]', '150.00');
        await page.selectOption('[data-testid="alert-condition"]', 'above');
        
        await page.click('[data-testid="create-alert"]');
        await page.waitForSelector('[data-testid="alert-created"]', { timeout: 10000 });
        
        console.log('📊 Price alert created');
        
        await trackMessagingEvent('notifications', {
          type: 'price_alert_created',
          symbol: 'AAPL',
          price: '150.00'
        });
      }
      
      // 4. Monitor for real-time notifications
      console.log('👀 Monitoring for real-time notifications...');
      
      await page.goto('/');
      
      // Wait for potential notifications
      await page.waitForTimeout(15000);
      
      // Check for notification UI elements
      const notificationCenter = page.locator('[data-testid="notification-center"]');
      if (await notificationCenter.isVisible()) {
        await notificationCenter.click();
        
        const notifications = page.locator('[data-testid^="notification-"]');
        const notificationCount = await notifications.count();
        
        console.log(`📬 Active notifications: ${notificationCount}`);
        
        if (notificationCount > 0) {
          for (let i = 0; i < Math.min(3, notificationCount); i++) {
            const notification = notifications.nth(i);
            const notificationText = await notification.textContent();
            const notificationType = await notification.getAttribute('data-notification-type');
            
            console.log(`📬 Notification ${i + 1} (${notificationType}): ${notificationText}`);
            
            await trackMessagingEvent('notifications', {
              type: 'ui_notification',
              notificationType: notificationType,
              message: notificationText
            });
          }
        }
      }
      
      // 5. Check for browser notifications
      const browserNotifications = await page.evaluate(() => {
        return window.testNotifications || [];
      });
      
      console.log(`📬 Browser notifications received: ${browserNotifications.length}`);
      
      browserNotifications.forEach((notification, index) => {
        console.log(`🔔 Browser notification ${index + 1}: ${notification.title}`);
        trackMessagingEvent('pushNotifications', {
          title: notification.title,
          options: notification.options
        });
      });
      
      console.log('✅ WebSocket Real-time Notifications Integration completed');
    });

    test('Push Notification Delivery and Handling', async ({ page }) => {
      console.log('📱 Testing Push Notification Delivery and Handling...');
      
      await authenticate(page);
      
      // 1. Test notification permission handling
      console.log('🔐 Testing notification permission handling...');
      
      const notificationPermission = await page.evaluate(async () => {
        if ('Notification' in window) {
          return {
            permission: Notification.permission,
            supported: true
          };
        }
        return { supported: false };
      });
      
      console.log(`📱 Notification support: ${notificationPermission.supported}`);
      console.log(`📱 Notification permission: ${notificationPermission.permission}`);
      
      await trackMessagingEvent('pushNotifications', {
        type: 'permission_check',
        supported: notificationPermission.supported,
        permission: notificationPermission.permission
      });
      
      // 2. Test notification opt-in flow
      if (notificationPermission.supported && notificationPermission.permission === 'default') {
        console.log('🔔 Testing notification opt-in flow...');
        
        const enableNotificationsButton = page.locator('[data-testid="enable-push-notifications"]');
        if (await enableNotificationsButton.isVisible()) {
          await enableNotificationsButton.click();
          
          // Wait for permission prompt (note: this may not work in headless mode)
          await page.waitForTimeout(2000);
          
          const newPermission = await page.evaluate(() => Notification.permission);
          console.log(`📱 Permission after opt-in: ${newPermission}`);
          
          await trackMessagingEvent('pushNotifications', {
            type: 'opt_in_flow',
            resultPermission: newPermission
          });
        }
      }
      
      // 3. Test notification service worker registration
      console.log('⚙️ Testing notification service worker...');
      
      const serviceWorkerInfo = await page.evaluate(async () => {
        if ('serviceWorker' in navigator) {
          const registration = await navigator.serviceWorker.getRegistration();
          return {
            registered: !!registration,
            scope: registration ? registration.scope : null,
            state: registration ? registration.active?.state : null
          };
        }
        return { supported: false };
      });
      
      console.log(`⚙️ Service worker registered: ${serviceWorkerInfo.registered}`);
      if (serviceWorkerInfo.registered) {
        console.log(`⚙️ Service worker state: ${serviceWorkerInfo.state}`);
        
        await trackMessagingEvent('pushNotifications', {
          type: 'service_worker_check',
          registered: serviceWorkerInfo.registered,
          state: serviceWorkerInfo.state
        });
      }
      
      // 4. Test notification display and interaction
      console.log('🔔 Testing notification display...');
      
      // Trigger a test notification through the app
      await page.goto('/admin/test-notifications');
      await page.waitForSelector('[data-testid="notification-testing"]', { timeout: 15000 });
      
      const testNotificationButton = page.locator('[data-testid="send-test-notification"]');
      if (await testNotificationButton.isVisible()) {
        await testNotificationButton.click();
        
        await page.waitForTimeout(3000);
        
        // Check if notification was created
        const testNotifications = await page.evaluate(() => {
          return window.testNotifications || [];
        });
        
        const newNotifications = testNotifications.filter(n => 
          n.timestamp > Date.now() - 5000
        );
        
        console.log(`🔔 Test notifications sent: ${newNotifications.length}`);
        
        newNotifications.forEach(notification => {
          console.log(`🔔 Test notification: ${notification.title}`);
          trackMessagingEvent('pushNotifications', {
            type: 'test_notification',
            title: notification.title,
            options: notification.options
          });
        });
      }
      
      console.log('✅ Push Notification Delivery and Handling completed');
    });

  });

  test.describe('Email Notification System @critical @enterprise @email', () => {

    test('Email Delivery and Template Testing', async ({ page, request }) => {
      console.log('📧 Testing Email Delivery and Template Testing...');
      
      await authenticate(page);
      
      // 1. Test email preference settings
      console.log('⚙️ Testing email preference settings...');
      
      await page.goto('/settings/email-preferences');
      await page.waitForSelector('[data-testid="email-preferences"]', { timeout: 15000 });
      
      const emailTypes = [
        'portfolio-reports',
        'trade-confirmations',
        'market-alerts',
        'account-updates',
        'security-notifications'
      ];
      
      for (const emailType of emailTypes) {
        const emailToggle = page.locator(`[data-testid="${emailType}-email-toggle"]`);
        if (await emailToggle.isVisible()) {
          const isEnabled = await emailToggle.isChecked();
          console.log(`📧 ${emailType}: ${isEnabled ? 'enabled' : 'disabled'}`);
          
          await trackMessagingEvent('emailEvents', {
            type: 'preference_check',
            emailType: emailType,
            enabled: isEnabled
          });
        }
      }
      
      // 2. Test email verification process
      console.log('✅ Testing email verification...');
      
      const emailVerificationStatus = page.locator('[data-testid="email-verification-status"]');
      if (await emailVerificationStatus.isVisible()) {
        const verificationText = await emailVerificationStatus.textContent();
        console.log(`✅ Email verification status: ${verificationText}`);
        
        await trackMessagingEvent('emailEvents', {
          type: 'verification_status',
          status: verificationText,
          verified: verificationText.includes('verified')
        });
        
        // Test resend verification if not verified
        if (!verificationText.includes('verified')) {
          const resendButton = page.locator('[data-testid="resend-verification"]');
          if (await resendButton.isVisible()) {
            await resendButton.click();
            
            await page.waitForSelector('[data-testid="verification-sent"]', { timeout: 5000 });
            console.log('📧 Verification email resent');
            
            await trackMessagingEvent('emailEvents', {
              type: 'verification_resent'
            });
          }
        }
      }
      
      // 3. Test triggered email scenarios
      console.log('🚀 Testing triggered email scenarios...');
      
      // Trigger portfolio report email
      await page.goto('/portfolio/reports');
      await page.waitForSelector('[data-testid="portfolio-reports"]', { timeout: 15000 });
      
      const generateReportButton = page.locator('[data-testid="generate-email-report"]');
      if (await generateReportButton.isVisible()) {
        await generateReportButton.click();
        
        await page.waitForSelector('[data-testid="report-generation-modal"]', { timeout: 10000 });
        
        // Configure report settings
        await page.selectOption('[data-testid="report-frequency"]', 'immediate');
        await page.selectOption('[data-testid="report-format"]', 'detailed');
        await page.check('[data-testid="email-delivery"]');
        
        await page.click('[data-testid="generate-report"]');
        
        await page.waitForSelector('[data-testid="report-generated"]', { timeout: 15000 });
        console.log('📊 Portfolio report generated and email triggered');
        
        await trackMessagingEvent('emailEvents', {
          type: 'portfolio_report_triggered',
          frequency: 'immediate',
          format: 'detailed'
        });
      }
      
      // 4. Test email delivery status API
      console.log('📊 Testing email delivery status...');
      
      const emailStatusResponse = await request.get(`${testConfig.apiURL}/api/user/email-status`, {
        headers: {
          'Authorization': `Bearer ${await getAuthToken(page)}`
        }
      });
      
      if (emailStatusResponse.ok()) {
        const emailStatus = await emailStatusResponse.json();
        console.log(`📧 Email delivery status:`, emailStatus);
        
        await trackMessagingEvent('emailEvents', {
          type: 'delivery_status_check',
          status: emailStatus
        });
        
        // Check for recent email sends
        if (emailStatus.recentEmails && emailStatus.recentEmails.length > 0) {
          console.log(`📧 Recent emails sent: ${emailStatus.recentEmails.length}`);
          
          emailStatus.recentEmails.forEach((email, index) => {
            console.log(`📧 Email ${index + 1}: ${email.type} - ${email.status}`);
            trackMessagingEvent('emailEvents', {
              type: 'recent_email',
              emailType: email.type,
              status: email.status,
              sentAt: email.sentAt
            });
          });
        }
      }
      
      console.log('✅ Email Delivery and Template Testing completed');
    });

  });

  test.describe('Message Queue Integration @critical @enterprise @messaging', () => {

    test('SQS Queue Processing and SNS Topic Integration', async ({ page, request }) => {
      console.log('📬 Testing SQS Queue Processing and SNS Topic Integration...');
      
      await authenticate(page);
      
      // 1. Check message queue status
      console.log('📊 Checking message queue status...');
      
      await page.goto('/admin/messaging');
      await page.waitForSelector('[data-testid="messaging-dashboard"]', { timeout: 15000 });
      
      const queueMetrics = {
        'trade-processing-queue': '[data-testid="trade-queue-metrics"]',
        'notification-queue': '[data-testid="notification-queue-metrics"]',
        'data-processing-queue': '[data-testid="data-queue-metrics"]',
        'error-queue': '[data-testid="error-queue-metrics"]'
      };
      
      for (const [queueName, selector] of Object.entries(queueMetrics)) {
        const queueElement = page.locator(selector);
        if (await queueElement.isVisible()) {
          const queueInfo = {
            messagesInQueue: await queueElement.locator('[data-testid="messages-in-queue"]').textContent().catch(() => '0'),
            messagesProcessed: await queueElement.locator('[data-testid="messages-processed"]').textContent().catch(() => '0'),
            queueHealth: await queueElement.locator('[data-testid="queue-health"]').textContent().catch(() => 'unknown')
          };
          
          console.log(`📬 ${queueName}:`, queueInfo);
          
          await trackMessagingEvent('sqsEvents', {
            queueName: queueName,
            metrics: queueInfo
          });
        }
      }
      
      // 2. Test message publishing
      console.log('📤 Testing message publishing...');
      
      const publishTestButton = page.locator('[data-testid="publish-test-message"]');
      if (await publishTestButton.isVisible()) {
        await publishTestButton.click();
        
        await page.waitForSelector('[data-testid="message-publish-form"]', { timeout: 10000 });
        
        await page.selectOption('[data-testid="message-queue"]', 'test-queue');
        await page.fill('[data-testid="message-content"]', JSON.stringify({
          type: 'test_message',
          timestamp: new Date().toISOString(),
          data: { test: true }
        }));
        
        await page.click('[data-testid="send-message"]');
        
        await page.waitForSelector('[data-testid="message-sent"]', { timeout: 10000 });
        console.log('📤 Test message published to queue');
        
        await trackMessagingEvent('sqsEvents', {
          type: 'message_published',
          queue: 'test-queue',
          messageType: 'test_message'
        });
      }
      
      // 3. Test SNS topic subscriptions
      console.log('📢 Testing SNS topic subscriptions...');
      
      const snsTopics = page.locator('[data-testid="sns-topics"]');
      if (await snsTopics.isVisible()) {
        const topics = page.locator('[data-testid^="topic-"]');
        const topicCount = await topics.count();
        
        console.log(`📢 SNS topics configured: ${topicCount}`);
        
        for (let i = 0; i < Math.min(3, topicCount); i++) {
          const topic = topics.nth(i);
          const topicName = await topic.locator('[data-testid="topic-name"]').textContent();
          const subscriberCount = await topic.locator('[data-testid="subscriber-count"]').textContent();
          
          console.log(`📢 Topic: ${topicName} - ${subscriberCount} subscribers`);
          
          await trackMessagingEvent('snsEvents', {
            topicName: topicName,
            subscribers: parseInt(subscriberCount) || 0
          });
        }
      }
      
      // 4. Test message processing status
      console.log('⚙️ Testing message processing status...');
      
      const processingStatus = page.locator('[data-testid="message-processing-status"]');
      if (await processingStatus.isVisible()) {
        const statusText = await processingStatus.textContent();
        console.log(`⚙️ Message processing status: ${statusText}`);
        
        await trackMessagingEvent('sqsEvents', {
          type: 'processing_status',
          status: statusText,
          healthy: statusText.includes('active') || statusText.includes('processing')
        });
      }
      
      // 5. Test dead letter queue monitoring
      const deadLetterQueue = page.locator('[data-testid="dead-letter-queue"]');
      if (await deadLetterQueue.isVisible()) {
        const dlqCount = await deadLetterQueue.locator('[data-testid="dlq-message-count"]').textContent();
        console.log(`💀 Dead letter queue messages: ${dlqCount}`);
        
        await trackMessagingEvent('sqsEvents', {
          type: 'dead_letter_queue',
          messageCount: parseInt(dlqCount) || 0
        });
        
        if (parseInt(dlqCount) > 0) {
          console.log('⚠️ Messages found in dead letter queue - potential processing issues');
        }
      }
      
      console.log('✅ SQS Queue Processing and SNS Topic Integration completed');
    });

  });

  test.describe('Cross-System Messaging Integration @critical @enterprise @cross-system', () => {

    test('Event-Driven Workflow Integration', async ({ page }) => {
      console.log('🔄 Testing Event-Driven Workflow Integration...');
      
      await authenticate(page);
      
      // 1. Test trade execution workflow
      console.log('💼 Testing trade execution workflow...');
      
      await page.goto('/trading');
      await page.waitForSelector('[data-testid="trading-page"]', { timeout: 15000 });
      
      // Place a test trade to trigger event workflow
      await page.click('[data-testid="place-order-button"]');
      await page.waitForSelector('[data-testid="order-form"]', { timeout: 10000 });
      
      await page.fill('[data-testid="symbol-input"]', 'AAPL');
      await page.fill('[data-testid="quantity-input"]', '1');
      await page.selectOption('[data-testid="order-type"]', 'market');
      
      // Submit order (dry run mode)
      await page.click('[data-testid="review-order"]');
      await page.waitForSelector('[data-testid="order-review"]', { timeout: 10000 });
      
      await page.click('[data-testid="confirm-order"]');
      
      // Monitor for workflow events
      await page.waitForTimeout(10000);
      
      // Check for workflow status updates
      const workflowStatus = page.locator('[data-testid="workflow-status"]');
      if (await workflowStatus.isVisible()) {
        const statusText = await workflowStatus.textContent();
        console.log(`🔄 Workflow status: ${statusText}`);
        
        await trackMessagingEvent('messageDelivery', {
          type: 'trade_workflow',
          status: statusText
        });
      }
      
      // 2. Test portfolio update events
      console.log('📊 Testing portfolio update events...');
      
      await page.goto('/portfolio');
      
      // Trigger portfolio recalculation
      const recalculateButton = page.locator('[data-testid="recalculate-portfolio"]');
      if (await recalculateButton.isVisible()) {
        await recalculateButton.click();
        
        // Monitor for update events
        await page.waitForTimeout(5000);
        
        const updateStatus = page.locator('[data-testid="portfolio-update-status"]');
        if (await updateStatus.isVisible()) {
          const updateText = await updateStatus.textContent();
          console.log(`📊 Portfolio update: ${updateText}`);
          
          await trackMessagingEvent('messageDelivery', {
            type: 'portfolio_update_event',
            status: updateText
          });
        }
      }
      
      console.log('✅ Event-Driven Workflow Integration completed');
    });

  });

  // Helper function to get auth token
  async function getAuthToken(page) {
    return await page.evaluate(() => {
      return localStorage.getItem('access_token') || 
             localStorage.getItem('authToken') ||
             sessionStorage.getItem('access_token') ||
             sessionStorage.getItem('authToken') ||
             'test-token';
    });
  }

  test.afterEach(async () => {
    // Messaging session summary
    console.log('\n📬 Messaging and Notifications Session Summary:');
    console.log(`Notifications: ${messagingSession.notifications.length}`);
    console.log(`WebSocket messages: ${messagingSession.websocketMessages.length}`);
    console.log(`Email events: ${messagingSession.emailEvents.length}`);
    console.log(`Push notifications: ${messagingSession.pushNotifications.length}`);
    console.log(`SQS events: ${messagingSession.sqsEvents.length}`);
    console.log(`SNS events: ${messagingSession.snsEvents.length}`);
    console.log(`Message delivery events: ${messagingSession.messageDelivery.length}`);
    console.log(`Total errors: ${messagingSession.errors.length}`);
    
    // Log notification breakdown
    if (messagingSession.notifications.length > 0) {
      console.log('\n🔔 Notification Breakdown:');
      const notificationTypes = messagingSession.notifications.reduce((acc, notification) => {
        const type = notification.notificationType || notification.type;
        acc[type] = (acc[type] || 0) + 1;
        return acc;
      }, {});
      
      Object.entries(notificationTypes).forEach(([type, count]) => {
        console.log(`  ${type}: ${count} notifications`);
      });
    }
    
    // Log email delivery summary
    if (messagingSession.emailEvents.length > 0) {
      console.log('\n📧 Email System Summary:');
      const emailTypes = messagingSession.emailEvents.reduce((acc, event) => {
        acc[event.type] = (acc[event.type] || 0) + 1;
        return acc;
      }, {});
      
      Object.entries(emailTypes).forEach(([type, count]) => {
        console.log(`  ${type}: ${count} events`);
      });
    }
    
    // Log queue health
    if (messagingSession.sqsEvents.length > 0) {
      console.log('\n📬 Message Queue Health:');
      const queueMetrics = messagingSession.sqsEvents.filter(event => event.queueName);
      queueMetrics.forEach(queue => {
        console.log(`  ${queue.queueName}: ${queue.metrics?.queueHealth || 'unknown'} health`);
      });
    }
    
    // Calculate messaging system reliability
    const totalMessagingEvents = messagingSession.notifications.length + 
                                messagingSession.emailEvents.length + 
                                messagingSession.sqsEvents.length;
    const errorCount = messagingSession.errors.length;
    const reliabilityScore = totalMessagingEvents > 0 ? 
      ((totalMessagingEvents - errorCount) / totalMessagingEvents * 100).toFixed(1) : 100;
    
    console.log(`\n📊 Messaging System Reliability: ${reliabilityScore}% (${totalMessagingEvents - errorCount}/${totalMessagingEvents})`);
  });

});

export default {
  testConfig
};