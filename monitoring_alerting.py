#!/usr/bin/env python3
"""
Real-time Monitoring and Alerting System
Performance tracking, data quality alerts, and system health monitoring
"""

import json
import logging
import smtplib
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from email.mime.multipart import MimeMultipart
from email.mime.text import MimeText
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd


class AlertSeverity(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(Enum):
    PERFORMANCE = "PERFORMANCE"
    DATA_QUALITY = "DATA_QUALITY"
    SYSTEM_HEALTH = "SYSTEM_HEALTH"
    TRADING_SIGNAL = "TRADING_SIGNAL"
    PORTFOLIO = "PORTFOLIO"
    MARKET_EVENT = "MARKET_EVENT"


@dataclass
class Alert:
    id: str
    timestamp: datetime
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    message: str
    data: Dict
    source: str
    resolved: bool = False
    resolved_timestamp: Optional[datetime] = None


@dataclass
class MetricThreshold:
    metric_name: str
    threshold_value: float
    comparison: str  # 'gt', 'lt', 'eq', 'gte', 'lte'
    severity: AlertSeverity
    alert_type: AlertType


@dataclass
class SystemMetrics:
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    api_response_time: float
    database_connections: int
    active_users: int
    data_freshness: float  # Minutes since last data update


class BaseMonitor(ABC):
    """Base class for monitoring components"""

    def __init__(self, name: str, check_interval: int = 60):
        self.name = name
        self.check_interval = check_interval
        self.last_check = None
        self.is_running = False
        self.logger = logging.getLogger(name)

    @abstractmethod
    def check(self) -> List[Alert]:
        pass

    def start_monitoring(self):
        self.is_running = True
        threading.Thread(target=self._monitor_loop, daemon=True).start()

    def stop_monitoring(self):
        self.is_running = False

    def _monitor_loop(self):
        while self.is_running:
            try:
                alerts = self.check()
                if alerts:
                    for alert in alerts:
                        self.logger.info(f"Alert generated: {alert.title}")
            except Exception as e:
                self.logger.error(f"Error in monitor {self.name}: {e}")

            time.sleep(self.check_interval)


class PerformanceMonitor(BaseMonitor):
    """Monitor system and application performance metrics"""

    def __init__(self, thresholds: List[MetricThreshold]):
        super().__init__("PerformanceMonitor", check_interval=30)
        self.thresholds = thresholds
        self.metrics_history: List[SystemMetrics] = []

    def check(self) -> List[Alert]:
        alerts = []

        # Get current system metrics
        current_metrics = self._collect_system_metrics()
        self.metrics_history.append(current_metrics)

        # Keep only last 1000 metrics
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]

        # Check against thresholds
        for threshold in self.thresholds:
            value = getattr(current_metrics, threshold.metric_name, None)

            if value is not None and self._check_threshold(value, threshold):
                alert = Alert(
                    id=f"perf_{threshold.metric_name}_{int(time.time())}",
                    timestamp=datetime.now(),
                    alert_type=threshold.alert_type,
                    severity=threshold.severity,
                    title=f"Performance Alert: {threshold.metric_name}",
                    message=f"{threshold.metric_name} is {value:.2f}, exceeding threshold of {threshold.threshold_value}",
                    data={
                        "metric_name": threshold.metric_name,
                        "current_value": value,
                        "threshold_value": threshold.threshold_value,
                        "comparison": threshold.comparison,
                    },
                    source=self.name,
                )
                alerts.append(alert)

        return alerts

    def _collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics"""
        try:
            import psutil

            # Get system metrics
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            # Mock other metrics (would integrate with actual monitoring)
            api_response_time = np.random.normal(150, 50)  # ms
            database_connections = np.random.randint(5, 25)
            active_users = np.random.randint(10, 100)
            data_freshness = np.random.uniform(0, 30)  # minutes

            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_usage=cpu_usage,
                memory_usage=memory.percent,
                disk_usage=disk.percent,
                api_response_time=max(0, api_response_time),
                database_connections=database_connections,
                active_users=active_users,
                data_freshness=data_freshness,
            )

        except ImportError:
            # Fallback if psutil not available
            return SystemMetrics(
                timestamp=datetime.now(),
                cpu_usage=np.random.uniform(10, 90),
                memory_usage=np.random.uniform(20, 80),
                disk_usage=np.random.uniform(30, 70),
                api_response_time=np.random.uniform(100, 500),
                database_connections=np.random.randint(5, 25),
                active_users=np.random.randint(10, 100),
                data_freshness=np.random.uniform(0, 30),
            )

    def _check_threshold(self, value: float, threshold: MetricThreshold) -> bool:
        """Check if value exceeds threshold"""
        comparison = threshold.comparison
        threshold_value = threshold.threshold_value

        if comparison == "gt":
            return value > threshold_value
        elif comparison == "lt":
            return value < threshold_value
        elif comparison == "gte":
            return value >= threshold_value
        elif comparison == "lte":
            return value <= threshold_value
        elif comparison == "eq":
            return abs(value - threshold_value) < 0.001

        return False

    def get_performance_summary(self) -> Dict:
        """Get performance summary over recent period"""
        if not self.metrics_history:
            return {}

        recent_metrics = self.metrics_history[-100:]  # Last 100 data points

        return {
            "avg_cpu_usage": np.mean([m.cpu_usage for m in recent_metrics]),
            "avg_memory_usage": np.mean([m.memory_usage for m in recent_metrics]),
            "avg_response_time": np.mean([m.api_response_time for m in recent_metrics]),
            "max_response_time": np.max([m.api_response_time for m in recent_metrics]),
            "data_points": len(recent_metrics),
            "time_span_minutes": (
                recent_metrics[-1].timestamp - recent_metrics[0].timestamp
            ).total_seconds()
            / 60,
        }


class DataQualityMonitor(BaseMonitor):
    """Monitor data quality and freshness"""

    def __init__(self, data_sources: List[str]):
        super().__init__("DataQualityMonitor", check_interval=300)  # 5 minutes
        self.data_sources = data_sources
        self.last_data_update = {}
        self.quality_scores = {}

    def check(self) -> List[Alert]:
        alerts = []

        for source in self.data_sources:
            # Check data freshness
            last_update = self.last_data_update.get(source)
            if last_update:
                minutes_since_update = (
                    datetime.now() - last_update
                ).total_seconds() / 60

                if minutes_since_update > 60:  # More than 1 hour
                    alert = Alert(
                        id=f"data_freshness_{source}_{int(time.time())}",
                        timestamp=datetime.now(),
                        alert_type=AlertType.DATA_QUALITY,
                        severity=(
                            AlertSeverity.HIGH
                            if minutes_since_update > 120
                            else AlertSeverity.MEDIUM
                        ),
                        title=f"Stale Data Alert: {source}",
                        message=f"Data for {source} is {minutes_since_update:.1f} minutes old",
                        data={
                            "source": source,
                            "minutes_since_update": minutes_since_update,
                            "last_update": last_update.isoformat(),
                        },
                        source=self.name,
                    )
                    alerts.append(alert)

            # Check data quality score
            quality_score = self.quality_scores.get(source, 100)
            if quality_score < 70:  # Quality score below 70%
                alert = Alert(
                    id=f"data_quality_{source}_{int(time.time())}",
                    timestamp=datetime.now(),
                    alert_type=AlertType.DATA_QUALITY,
                    severity=(
                        AlertSeverity.HIGH
                        if quality_score < 50
                        else AlertSeverity.MEDIUM
                    ),
                    title=f"Data Quality Alert: {source}",
                    message=f"Data quality score for {source} is {quality_score:.1f}%",
                    data={"source": source, "quality_score": quality_score},
                    source=self.name,
                )
                alerts.append(alert)

        return alerts

    def update_data_timestamp(self, source: str, timestamp: Optional[datetime] = None):
        """Update last data timestamp for a source"""
        self.last_data_update[source] = timestamp or datetime.now()

    def update_quality_score(self, source: str, score: float):
        """Update quality score for a source"""
        self.quality_scores[source] = score


class PortfolioMonitor(BaseMonitor):
    """Monitor portfolio performance and risk metrics"""

    def __init__(self, portfolio_thresholds: Dict[str, float]):
        super().__init__("PortfolioMonitor", check_interval=60)
        self.portfolio_thresholds = portfolio_thresholds
        self.portfolio_metrics = {}

    def check(self) -> List[Alert]:
        alerts = []

        # Check portfolio metrics against thresholds
        for metric, current_value in self.portfolio_metrics.items():
            threshold = self.portfolio_thresholds.get(metric)

            if threshold is not None:
                if metric == "max_drawdown" and current_value > threshold:
                    alert = Alert(
                        id=f"portfolio_{metric}_{int(time.time())}",
                        timestamp=datetime.now(),
                        alert_type=AlertType.PORTFOLIO,
                        severity=AlertSeverity.HIGH,
                        title=f"Portfolio Risk Alert: {metric}",
                        message=f"{metric} is {current_value:.1%}, exceeding threshold of {threshold:.1%}",
                        data={
                            "metric": metric,
                            "current_value": current_value,
                            "threshold": threshold,
                        },
                        source=self.name,
                    )
                    alerts.append(alert)

                elif (
                    metric == "var_95" and current_value < threshold
                ):  # VaR is negative
                    alert = Alert(
                        id=f"portfolio_{metric}_{int(time.time())}",
                        timestamp=datetime.now(),
                        alert_type=AlertType.PORTFOLIO,
                        severity=AlertSeverity.MEDIUM,
                        title=f"Portfolio Risk Alert: {metric}",
                        message=f"Value at Risk (95%) is ${current_value:,.0f}",
                        data={
                            "metric": metric,
                            "current_value": current_value,
                            "threshold": threshold,
                        },
                        source=self.name,
                    )
                    alerts.append(alert)

        return alerts

    def update_portfolio_metrics(self, metrics: Dict[str, float]):
        """Update portfolio metrics"""
        self.portfolio_metrics.update(metrics)


class TradingSignalMonitor(BaseMonitor):
    """Monitor for trading signals and market events"""

    def __init__(self, signal_thresholds: Dict[str, float]):
        super().__init__("TradingSignalMonitor", check_interval=30)
        self.signal_thresholds = signal_thresholds
        self.active_signals = {}

    def check(self) -> List[Alert]:
        alerts = []

        # Check for strong trading signals
        for signal_type, signals in self.active_signals.items():
            for symbol, signal_strength in signals.items():
                threshold = self.signal_thresholds.get(signal_type, 0.8)

                if abs(signal_strength) >= threshold:
                    direction = "BUY" if signal_strength > 0 else "SELL"

                    alert = Alert(
                        id=f"signal_{signal_type}_{symbol}_{int(time.time())}",
                        timestamp=datetime.now(),
                        alert_type=AlertType.TRADING_SIGNAL,
                        severity=AlertSeverity.MEDIUM,
                        title=f"Trading Signal: {direction} {symbol}",
                        message=f"{signal_type} signal for {symbol}: {signal_strength:.2f}",
                        data={
                            "symbol": symbol,
                            "signal_type": signal_type,
                            "signal_strength": signal_strength,
                            "direction": direction,
                        },
                        source=self.name,
                    )
                    alerts.append(alert)

        return alerts

    def update_signals(self, signal_type: str, signals: Dict[str, float]):
        """Update trading signals"""
        if signal_type not in self.active_signals:
            self.active_signals[signal_type] = {}
        self.active_signals[signal_type].update(signals)


class AlertManager:
    """Manages alerts, notifications, and escalations"""

    def __init__(self, email_config: Optional[Dict] = None):
        self.alerts: List[Alert] = []
        self.email_config = email_config
        self.notification_rules = {
            AlertSeverity.CRITICAL: ["email", "sms"],
            AlertSeverity.HIGH: ["email"],
            AlertSeverity.MEDIUM: ["email"],
            AlertSeverity.LOW: ["log"],
        }
        self.escalation_times = {
            AlertSeverity.CRITICAL: 300,  # 5 minutes
            AlertSeverity.HIGH: 900,  # 15 minutes
            AlertSeverity.MEDIUM: 1800,  # 30 minutes
            AlertSeverity.LOW: 3600,  # 1 hour
        }

    def add_alert(self, alert: Alert):
        """Add a new alert"""
        self.alerts.append(alert)
        self._process_alert(alert)

    def resolve_alert(self, alert_id: str):
        """Resolve an alert"""
        for alert in self.alerts:
            if alert.id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_timestamp = datetime.now()
                break

    def get_active_alerts(
        self, severity: Optional[AlertSeverity] = None
    ) -> List[Alert]:
        """Get active (unresolved) alerts"""
        active = [a for a in self.alerts if not a.resolved]

        if severity:
            active = [a for a in active if a.severity == severity]

        return sorted(active, key=lambda x: x.timestamp, reverse=True)

    def get_alert_summary(self, hours_back: int = 24) -> Dict:
        """Get summary of alerts over specified period"""
        cutoff = datetime.now() - timedelta(hours=hours_back)
        recent_alerts = [a for a in self.alerts if a.timestamp >= cutoff]

        by_severity = {}
        by_type = {}

        for alert in recent_alerts:
            # Count by severity
            sev = alert.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # Count by type
            typ = alert.alert_type.value
            by_type[typ] = by_type.get(typ, 0) + 1

        return {
            "total_alerts": len(recent_alerts),
            "active_alerts": len([a for a in recent_alerts if not a.resolved]),
            "by_severity": by_severity,
            "by_type": by_type,
            "period_hours": hours_back,
            "most_recent": (
                recent_alerts[0].timestamp.isoformat() if recent_alerts else None
            ),
        }

    def _process_alert(self, alert: Alert):
        """Process alert based on severity and rules"""
        notification_methods = self.notification_rules.get(alert.severity, ["log"])

        for method in notification_methods:
            if method == "email":
                self._send_email_alert(alert)
            elif method == "sms":
                self._send_sms_alert(alert)
            elif method == "log":
                self._log_alert(alert)

    def _send_email_alert(self, alert: Alert):
        """Send email notification"""
        if not self.email_config:
            self._log_alert(alert)
            return

        try:
            # Create email message
            msg = MimeMultipart()
            msg["From"] = self.email_config["from"]
            msg["To"] = ", ".join(self.email_config["to"])
            msg["Subject"] = f"[{alert.severity.value}] {alert.title}"

            body = f"""
Alert Details:
- Type: {alert.alert_type.value}
- Severity: {alert.severity.value}
- Time: {alert.timestamp}
- Source: {alert.source}

Message: {alert.message}

Data: {json.dumps(alert.data, indent=2)}
            """

            msg.attach(MimeText(body, "plain"))

            # Send email
            server = smtplib.SMTP(
                self.email_config["smtp_server"], self.email_config["smtp_port"]
            )
            if self.email_config.get("username"):
                server.starttls()
                server.login(
                    self.email_config["username"], self.email_config["password"]
                )

            server.send_message(msg)
            server.quit()

        except Exception as e:
            print(f"Failed to send email alert: {e}")
            self._log_alert(alert)

    def _send_sms_alert(self, alert: Alert):
        """Send SMS notification (placeholder)"""
        # Would integrate with SMS service (Twilio, etc.)
        print(f"SMS Alert: {alert.title} - {alert.message}")

    def _log_alert(self, alert: Alert):
        """Log alert to console/file"""
        print(f"[{alert.timestamp}] {alert.severity.value}: {alert.title}")
        print(f"  Source: {alert.source}")
        print(f"  Message: {alert.message}")


class MonitoringSystem:
    """
    Main monitoring and alerting system
    Coordinates all monitors and manages alerts
    """

    def __init__(self, email_config: Optional[Dict] = None):
        self.alert_manager = AlertManager(email_config)
        self.monitors: List[BaseMonitor] = []
        self.is_running = False

        # Default thresholds
        performance_thresholds = [
            MetricThreshold(
                "cpu_usage", 80.0, "gt", AlertSeverity.HIGH, AlertType.SYSTEM_HEALTH
            ),
            MetricThreshold(
                "memory_usage", 85.0, "gt", AlertSeverity.HIGH, AlertType.SYSTEM_HEALTH
            ),
            MetricThreshold(
                "api_response_time",
                1000.0,
                "gt",
                AlertSeverity.MEDIUM,
                AlertType.PERFORMANCE,
            ),
            MetricThreshold(
                "data_freshness",
                30.0,
                "gt",
                AlertSeverity.MEDIUM,
                AlertType.DATA_QUALITY,
            ),
        ]

        # Initialize monitors
        self.performance_monitor = PerformanceMonitor(performance_thresholds)
        self.data_quality_monitor = DataQualityMonitor(
            ["price_data", "financial_data", "news_data"]
        )
        self.portfolio_monitor = PortfolioMonitor(
            {"max_drawdown": 0.15, "var_95": -50000}
        )
        self.trading_signal_monitor = TradingSignalMonitor(
            {"momentum": 0.8, "pattern": 0.7}
        )

        self.monitors = [
            self.performance_monitor,
            self.data_quality_monitor,
            self.portfolio_monitor,
            self.trading_signal_monitor,
        ]

    def start_monitoring(self):
        """Start all monitoring components"""
        self.is_running = True

        for monitor in self.monitors:
            monitor.start_monitoring()

        # Start alert collection thread
        threading.Thread(target=self._collect_alerts, daemon=True).start()

        print("Monitoring system started")

    def stop_monitoring(self):
        """Stop all monitoring"""
        self.is_running = False

        for monitor in self.monitors:
            monitor.stop_monitoring()

        print("Monitoring system stopped")

    def _collect_alerts(self):
        """Collect alerts from all monitors"""
        while self.is_running:
            try:
                for monitor in self.monitors:
                    if hasattr(monitor, "_alerts_queue"):
                        alerts = getattr(monitor, "_alerts_queue", [])
                        for alert in alerts:
                            self.alert_manager.add_alert(alert)
                        monitor._alerts_queue = []
            except Exception as e:
                print(f"Error collecting alerts: {e}")

            time.sleep(5)

    def get_system_status(self) -> Dict:
        """Get comprehensive system status"""
        return {
            "monitoring_active": self.is_running,
            "active_monitors": len([m for m in self.monitors if m.is_running]),
            "total_monitors": len(self.monitors),
            "performance_summary": self.performance_monitor.get_performance_summary(),
            "alert_summary": self.alert_manager.get_alert_summary(),
            "system_timestamp": datetime.now().isoformat(),
        }

    def trigger_test_alert(self, severity: AlertSeverity = AlertSeverity.MEDIUM):
        """Trigger a test alert for testing purposes"""
        test_alert = Alert(
            id=f"test_{int(time.time())}",
            timestamp=datetime.now(),
            alert_type=AlertType.SYSTEM_HEALTH,
            severity=severity,
            title="Test Alert",
            message="This is a test alert to verify the monitoring system",
            data={"test": True},
            source="MonitoringSystem",
        )

        self.alert_manager.add_alert(test_alert)
        return test_alert.id


def main():
    """Example usage of monitoring and alerting system"""
    print("Real-time Monitoring and Alerting System")
    print("=" * 45)

    # Initialize monitoring system
    monitoring_system = MonitoringSystem()

    # Start monitoring
    monitoring_system.start_monitoring()

    print("Monitoring system is running...")
    print("Waiting for alerts...")

    # Simulate some events
    time.sleep(2)

    # Update some metrics to trigger alerts
    monitoring_system.data_quality_monitor.update_quality_score(
        "price_data", 45.0
    )  # Low quality
    monitoring_system.portfolio_monitor.update_portfolio_metrics(
        {"max_drawdown": 0.18}
    )  # High drawdown

    # Trigger test alert
    test_id = monitoring_system.trigger_test_alert(AlertSeverity.HIGH)
    print(f"Triggered test alert: {test_id}")

    time.sleep(3)

    # Get system status
    status = monitoring_system.get_system_status()
    print(f"\nSystem Status:")
    print(f"  Active Monitors: {status['active_monitors']}/{status['total_monitors']}")
    print(f"  Total Alerts (24h): {status['alert_summary']['total_alerts']}")
    print(f"  Active Alerts: {status['alert_summary']['active_alerts']}")

    # Show recent alerts
    recent_alerts = monitoring_system.alert_manager.get_active_alerts()
    if recent_alerts:
        print(f"\nRecent Alerts:")
        for alert in recent_alerts[:3]:  # Show first 3
            print(f"  {alert.severity.value}: {alert.title}")

    # Stop monitoring
    monitoring_system.stop_monitoring()


if __name__ == "__main__":
    main()
