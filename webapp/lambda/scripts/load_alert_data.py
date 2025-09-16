#!/usr/bin/env python3
"""
Enhanced Alert System Data Loader
Loads alert templates, settings, and sample data for development
"""
import json
import logging
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

def get_db_config():
    """Get database configuration"""
    return {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "5432")),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "password"),
        "dbname": os.environ.get("DB_NAME", "stocks"),
    }

def get_sample_alert_data():
    """Generate sample alert data for development"""
    current_time = datetime.now()
    
    # Price alerts data
    price_alerts = [
        {
            'user_id': 'dev-user-bypass',
            'symbol': 'AAPL',
            'alert_type': 'price_target',
            'condition': 'above',
            'target_price': 190.00,
            'current_price': 185.25,
            'priority': 'high',
            'message': 'AAPL approaching breakout level',
            'notification_methods': '["email", "push"]',
            'expires_at': current_time + timedelta(days=30)
        },
        {
            'user_id': 'dev-user-bypass',
            'symbol': 'TSLA',
            'alert_type': 'price_target',
            'condition': 'below',
            'target_price': 200.00,
            'current_price': 215.50,
            'priority': 'medium',
            'message': 'TSLA support level watch',
            'notification_methods': '["email"]',
            'expires_at': current_time + timedelta(days=30)
        },
        {
            'user_id': 'dev-user-bypass',
            'symbol': 'NVDA',
            'alert_type': 'percentage_change',
            'condition': 'above',
            'target_price': 5.0,  # 5% change
            'current_price': 2.1,
            'priority': 'medium',
            'message': 'NVDA significant daily move',
            'notification_methods': '["push"]',
            'expires_at': current_time + timedelta(days=7)
        }
    ]
    
    # Risk alerts data
    risk_alerts = [
        {
            'user_id': 'dev-user-bypass',
            'symbol': 'SPY',
            'alert_type': 'volatility',
            'condition': 'above',
            'threshold_value': 25.0,
            'current_value': 18.5,
            'severity': 'medium',
            'message': 'Market volatility spike warning',
            'notification_methods': '["email", "push"]',
            'expires_at': current_time + timedelta(days=90)
        },
        {
            'user_id': 'dev-user-bypass',
            'symbol': None,
            'alert_type': 'portfolio_drawdown',
            'condition': 'above',
            'threshold_value': 10.0,
            'current_value': 5.2,
            'severity': 'high',
            'message': 'Portfolio drawdown alert',
            'notification_methods': '["email", "push", "sms"]',
            'expires_at': current_time + timedelta(days=365)
        }
    ]
    
    # Trading alerts data
    trading_alerts = [
        {
            'user_id': 'dev-user-bypass',
            'alert_id': f'volume_spike_{random.randint(1000, 9999)}',
            'symbol': 'AAPL',
            'alert_type': 'volume',
            'category': 'technical',
            'priority': 'medium',
            'condition_type': 'volume_above_average',
            'threshold_value': 2.0,
            'current_value': 1.5,
            'message': 'AAPL unusual volume detected',
            'metadata': json.dumps({
                'volume_multiplier': 2.0,
                'average_volume': 50000000,
                'current_volume': 75000000
            }),
            'notification_methods': '["email"]',
            'expires_at': current_time + timedelta(days=1)
        },
        {
            'user_id': 'dev-user-bypass',
            'alert_id': f'rsi_oversold_{random.randint(1000, 9999)}',
            'symbol': 'TSLA',
            'alert_type': 'technical',
            'category': 'technical',
            'priority': 'low',
            'condition_type': 'rsi_below',
            'threshold_value': 30.0,
            'current_value': 35.2,
            'message': 'TSLA RSI approaching oversold',
            'metadata': json.dumps({
                'indicator': 'RSI',
                'period': 14,
                'threshold': 30.0
            }),
            'notification_methods': '["push"]',
            'expires_at': current_time + timedelta(days=7)
        }
    ]
    
    return price_alerts, risk_alerts, trading_alerts

def get_alert_templates():
    """Get comprehensive alert templates"""
    return [
        {
            'template_name': 'Price Breakout Above Resistance',
            'template_type': 'price',
            'alert_config': json.dumps({
                'alert_type': 'price',
                'condition': 'crosses_above',
                'priority': 'high',
                'notification_methods': ['email', 'push'],
                'expires_days': 30,
                'metadata': {
                    'pattern_type': 'breakout',
                    'confirmation_required': True
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'Support Level Breach',
            'template_type': 'price',
            'alert_config': json.dumps({
                'alert_type': 'price',
                'condition': 'crosses_below',
                'priority': 'high',
                'notification_methods': ['email', 'push', 'sms'],
                'expires_days': 30,
                'metadata': {
                    'pattern_type': 'breakdown',
                    'stop_loss_suggestion': True
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'High Volume Spike',
            'template_type': 'volume',
            'alert_config': json.dumps({
                'alert_type': 'volume',
                'condition': 'volume_above_average',
                'threshold_multiplier': 3.0,
                'priority': 'medium',
                'notification_methods': ['push'],
                'expires_days': 1,
                'metadata': {
                    'pattern_type': 'volume_spike',
                    'min_average_volume': 1000000
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'RSI Overbought Alert',
            'template_type': 'technical',
            'alert_config': json.dumps({
                'alert_type': 'technical',
                'indicator': 'rsi',
                'condition': 'above',
                'threshold': 80.0,
                'priority': 'low',
                'notification_methods': ['email'],
                'expires_days': 7,
                'metadata': {
                    'indicator_period': 14,
                    'pattern_type': 'overbought'
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'RSI Oversold Alert',
            'template_type': 'technical',
            'alert_config': json.dumps({
                'alert_type': 'technical',
                'indicator': 'rsi',
                'condition': 'below',
                'threshold': 20.0,
                'priority': 'medium',
                'notification_methods': ['email', 'push'],
                'expires_days': 7,
                'metadata': {
                    'indicator_period': 14,
                    'pattern_type': 'oversold'
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'Earnings Announcement Reminder',
            'template_type': 'earnings',
            'alert_config': json.dumps({
                'alert_type': 'earnings',
                'condition': 'earnings_announcement',
                'days_before': 3,
                'priority': 'high',
                'notification_methods': ['email', 'push'],
                'metadata': {
                    'include_estimates': True,
                    'include_analyst_count': True
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'Portfolio Volatility Warning',
            'template_type': 'risk',
            'alert_config': json.dumps({
                'alert_type': 'volatility',
                'condition': 'above',
                'threshold': 25.0,
                'priority': 'high',
                'notification_methods': ['email', 'push'],
                'expires_days': 90,
                'metadata': {
                    'calculation_period': 30,
                    'risk_level': 'high'
                }
            }),
            'is_system_template': True
        },
        {
            'template_name': 'Major News Sentiment Alert',
            'template_type': 'news',
            'alert_config': json.dumps({
                'alert_type': 'news',
                'condition': 'sentiment_extreme',
                'sentiment_threshold': 0.8,
                'priority': 'medium',
                'notification_methods': ['push'],
                'expires_days': 1,
                'metadata': {
                    'include_headline': True,
                    'include_source': True
                }
            }),
            'is_system_template': True
        }
    ]

def get_webhook_configs():
    """Get sample webhook configurations"""
    return [
        {
            'user_id': 'dev-user-bypass',
            'webhook_id': f'slack_alerts_{random.randint(1000, 9999)}',
            'name': 'Slack Alerts Channel',
            'url': 'https://hooks.slack.com/services/EXAMPLE/WEBHOOK/URL',
            'webhook_type': 'slack',
            'events': json.dumps(['price_alert', 'volume_alert', 'earnings_alert']),
            'headers': json.dumps({
                'Content-Type': 'application/json'
            }),
            'enabled': False  # Disabled by default for development
        },
        {
            'user_id': 'dev-user-bypass',
            'webhook_id': f'discord_alerts_{random.randint(1000, 9999)}',
            'name': 'Discord Trading Channel',
            'url': 'https://discord.com/api/webhooks/EXAMPLE/WEBHOOK',
            'webhook_type': 'discord',
            'events': json.dumps(['price_alert', 'technical_alert']),
            'headers': json.dumps({
                'Content-Type': 'application/json'
            }),
            'enabled': False  # Disabled by default for development
        },
        {
            'user_id': 'dev-user-bypass',
            'webhook_id': f'custom_api_{random.randint(1000, 9999)}',
            'name': 'Custom API Endpoint',
            'url': 'https://httpbin.org/post',  # Test endpoint
            'webhook_type': 'custom',
            'events': json.dumps(['all']),
            'headers': json.dumps({
                'Content-Type': 'application/json',
                'Authorization': 'Bearer test-token'
            }),
            'enabled': True  # Enabled for testing
        }
    ]

def load_alert_data(cur, conn):
    """Load alert system data into database"""
    logging.info("Loading alert system data...")
    
    # Load alert settings for development user
    try:
        cur.execute("""
            INSERT INTO alert_settings (user_id, notification_preferences, delivery_settings, alert_categories, advanced_settings)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                notification_preferences = EXCLUDED.notification_preferences,
                delivery_settings = EXCLUDED.delivery_settings,
                alert_categories = EXCLUDED.alert_categories,
                advanced_settings = EXCLUDED.advanced_settings,
                updated_at = NOW()
        """, (
            'dev-user-bypass',
            json.dumps({
                "email_enabled": True,
                "sms_enabled": False,
                "push_enabled": True,
                "browser_enabled": True,
                "slack_enabled": True,
                "discord_enabled": False
            }),
            json.dumps({
                "time_zone": "America/New_York",
                "quiet_hours": {
                    "enabled": True,
                    "start_time": "22:00",
                    "end_time": "07:00"
                }
            }),
            json.dumps({
                "price_alerts": {"enabled": True, "threshold_percentage": 5.0},
                "volume_alerts": {"enabled": True, "threshold_multiplier": 2.0},
                "earnings_alerts": {"enabled": True, "pre_earnings_days": 3},
                "news_alerts": {"enabled": True, "sentiment_threshold": 0.7},
                "technical_alerts": {"enabled": True}
            }),
            json.dumps({
                "max_daily_alerts": 50,
                "duplicate_suppression": True,
                "suppression_window_minutes": 15
            })
        ))
        logging.info("Alert settings loaded successfully")
    except Exception as e:
        logging.error(f"Failed to load alert settings: {e}")
    
    # Load sample alert data
    price_alerts, risk_alerts, trading_alerts = get_sample_alert_data()
    
    # Load price alerts
    try:
        price_alert_values = []
        for alert in price_alerts:
            price_alert_values.append((
                alert['user_id'], alert['symbol'], alert['alert_type'],
                alert['condition'], alert['target_price'], alert['current_price'],
                alert['priority'], alert['notification_methods'], alert['message'],
                alert['expires_at']
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO price_alerts (
                user_id, symbol, alert_type, condition, target_price, 
                current_price, priority, notification_methods, message, expires_at
            ) VALUES %s
            ON CONFLICT (user_id, symbol, condition, target_price) DO UPDATE SET
                current_price = EXCLUDED.current_price,
                message = EXCLUDED.message,
                updated_at = NOW()
            """,
            price_alert_values
        )
        logging.info(f"Loaded {len(price_alert_values)} price alerts")
    except Exception as e:
        logging.error(f"Failed to load price alerts: {e}")
    
    # Load risk alerts
    try:
        risk_alert_values = []
        for alert in risk_alerts:
            risk_alert_values.append((
                alert['user_id'], alert['symbol'], alert['alert_type'],
                alert['condition'], alert['threshold_value'], alert['current_value'],
                alert['severity'], alert['notification_methods'], alert['message'],
                alert['expires_at']
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO risk_alerts (
                user_id, symbol, alert_type, condition, threshold_value,
                current_value, severity, notification_methods, message, expires_at
            ) VALUES %s
            ON CONFLICT DO NOTHING
            """,
            risk_alert_values
        )
        logging.info(f"Loaded {len(risk_alert_values)} risk alerts")
    except Exception as e:
        logging.error(f"Failed to load risk alerts: {e}")
    
    # Load trading alerts
    try:
        trading_alert_values = []
        for alert in trading_alerts:
            trading_alert_values.append((
                alert['user_id'], alert['alert_id'], alert['symbol'],
                alert['alert_type'], alert['category'], alert['priority'],
                alert['condition_type'], alert['threshold_value'], alert['current_value'],
                alert['message'], alert['metadata'], alert['notification_methods'],
                alert['expires_at']
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO trading_alerts (
                user_id, alert_id, symbol, alert_type, category, priority,
                condition_type, threshold_value, current_value, message,
                metadata, notification_methods, expires_at
            ) VALUES %s
            ON CONFLICT (alert_id) DO UPDATE SET
                message = EXCLUDED.message,
                current_value = EXCLUDED.current_value,
                updated_at = NOW()
            """,
            trading_alert_values
        )
        logging.info(f"Loaded {len(trading_alert_values)} trading alerts")
    except Exception as e:
        logging.error(f"Failed to load trading alerts: {e}")
    
    # Load alert templates
    try:
        templates = get_alert_templates()
        template_values = []
        for template in templates:
            template_values.append((
                template['template_name'],
                template['template_type'],
                template['alert_config'],
                template['is_system_template']
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO alert_templates (
                template_name, template_type, alert_config, is_system_template
            ) VALUES %s
            ON CONFLICT DO NOTHING
            """,
            template_values
        )
        logging.info(f"Loaded {len(template_values)} alert templates")
    except Exception as e:
        logging.error(f"Failed to load alert templates: {e}")
    
    # Load webhook configurations
    try:
        webhooks = get_webhook_configs()
        webhook_values = []
        for webhook in webhooks:
            webhook_values.append((
                webhook['user_id'], webhook['webhook_id'], webhook['name'],
                webhook['url'], webhook['webhook_type'], webhook['events'],
                webhook['headers'], webhook['enabled']
            ))
        
        execute_values(
            cur,
            """
            INSERT INTO alert_webhooks (
                user_id, webhook_id, name, url, webhook_type, events, headers, enabled
            ) VALUES %s
            ON CONFLICT (webhook_id) DO UPDATE SET
                name = EXCLUDED.name,
                url = EXCLUDED.url,
                enabled = EXCLUDED.enabled,
                updated_at = NOW()
            """,
            webhook_values
        )
        logging.info(f"Loaded {len(webhook_values)} webhook configurations")
    except Exception as e:
        logging.error(f"Failed to load webhook configurations: {e}")
    
    conn.commit()
    return len(price_alerts) + len(risk_alerts) + len(trading_alerts)

def cleanup_old_alerts(cur, conn):
    """Clean up old triggered alerts"""
    cleanup_date = datetime.now() - timedelta(days=30)
    
    # Clean up old price alerts
    cur.execute(
        "DELETE FROM price_alerts WHERE status = 'triggered' AND triggered_at < %s",
        (cleanup_date,)
    )
    price_deleted = cur.rowcount
    
    # Clean up old trading alerts
    cur.execute(
        "DELETE FROM trading_alerts WHERE status = 'triggered' AND last_triggered < %s",
        (cleanup_date,)
    )
    trading_deleted = cur.rowcount
    
    # Clean up old delivery history
    cur.execute(
        "DELETE FROM alert_delivery_history WHERE created_at < %s",
        (cleanup_date,)
    )
    delivery_deleted = cur.rowcount
    
    logging.info(f"Cleaned up {price_deleted} price alerts, {trading_deleted} trading alerts, {delivery_deleted} delivery records")
    conn.commit()
    return price_deleted + trading_deleted + delivery_deleted

if __name__ == "__main__":
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        dbname=cfg["dbname"],
    )
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Create tables if they don't exist
    try:
        with open('/home/stocks/algo/webapp/lambda/create_alert_tables.sql', 'r') as f:
            cur.execute(f.read())
        conn.commit()
        logging.info("Alert tables created/updated")
    except Exception as e:
        logging.error(f"Failed to create tables: {e}")
        # Continue anyway, tables might already exist
    
    # Load alert data
    loaded_count = load_alert_data(cur, conn)
    
    # Cleanup old data
    cleanup_count = cleanup_old_alerts(cur, conn)
    
    cur.close()
    conn.close()
    
    logging.info(f"Alert data loading complete. Loaded: {loaded_count}, Cleaned up: {cleanup_count}")