#!/usr/bin/env python3
"""
Loader SLA Monitor

Tracks loader execution times against SLA targets and provides alerts
when loaders are approaching or exceeding their time budgets.

SLA Targets (from steering/loader-strategy.md):
- stock_prices_daily: 20-30 min expected, 120 min alert threshold
- technical_data_daily: 15-25 min expected, 60 min alert threshold
- morning prep pipeline: 60-90 min total, 300 min alert threshold
"""

import logging
import time
from dataclasses import dataclass

# MetricsPublisher is optional (fail-open if not available)
try:
    from algo.reporting import MetricsPublisher
except ImportError:
    MetricsPublisher = None  # type: ignore


logger = logging.getLogger(__name__)

# SLA configuration per loader
# Format: {loader_name: (expected_seconds, warning_threshold_seconds, critical_threshold_seconds)}
LOADER_SLA_TARGETS = {
    # Critical loaders
    "stock_prices_daily": (
        20 * 60,
        90 * 60,
        120 * 60,
    ),  # Expect 20 min, warn at 90, critical at 120
    "stock_symbols": (10 * 60, 15 * 60, 30 * 60),
    "trend_template_data": (30 * 60, 60 * 60, 90 * 60),
    "market_health_daily": (20 * 60, 30 * 60, 60 * 60),
    "market_exposure_daily": (10 * 60, 20 * 60, 30 * 60),
    "algo_metrics_daily": (12 * 60, 60 * 60, 120 * 60),
    "technical_data_daily_vectorized": (20 * 60, 45 * 60, 60 * 60),
    "technical_data_daily": (60 * 60, 90 * 60, 120 * 60),  # Old non-vectorized version
    "buy_sell_daily": (30 * 60, 120 * 60, 180 * 60),
    "sector_ranking": (15 * 60, 20 * 60, 30 * 60),
    # Supporting loaders
    "earnings_calendar": (10 * 60, 30 * 60, 60 * 60),
    "analyst_sentiment_analysis": (20 * 60, 60 * 60, 120 * 60),
    "company_profile": (30 * 60, 120 * 60, 240 * 60),
    "sp500_constituents": (5 * 60, 10 * 60, 20 * 60),
    "russell2000_constituents": (5 * 60, 10 * 60, 20 * 60),
}

# Pipeline SLA targets (minute-based)
PIPELINE_SLA_TARGETS = {
    "morning_prep_pipeline": (
        90 * 60,
        240 * 60,
        300 * 60,
    ),  # 90 min expected, 5 hour max before 9:30 AM
    "eod_pipeline": (120 * 60, 240 * 60, 300 * 60),  # 2 hour expected, 5 hour max
    "afternoon_update_pipeline": (
        15 * 60,
        25 * 60,
        30 * 60,
    ),  # 15 min expected, 30 min max
    "preclose_update_pipeline": (
        15 * 60,
        25 * 60,
        30 * 60,
    ),  # 15 min expected, 30 min max
}


@dataclass
class SLAStatus:
    """Status of a loader against its SLA targets."""

    loader_name: str
    elapsed_seconds: float
    expected_seconds: float
    warning_threshold_seconds: float
    critical_threshold_seconds: float
    is_breaching: bool
    is_critical: bool
    margin_pct: float  # How much time is left as % of warning threshold
    recommendation: str = ""

    @property
    def status_emoji(self) -> str:
        if self.is_critical:
            return "🔴"
        elif self.is_breaching:
            return "🟡"
        elif self.margin_pct < 50:
            return "🟠"
        else:
            return "🟢"

    @property
    def status_text(self) -> str:
        if self.is_critical:
            return "CRITICAL"
        elif self.is_breaching:
            return "WARNING"
        else:
            return "OK"


class SLAMonitor:
    """Monitor loader execution times against SLA targets."""

    def __init__(self, loader_name: str):
        """Initialize SLA monitor for a loader.

        Args:
            loader_name: Name of the loader to monitor
        """
        self.loader_name = loader_name
        self.start_time: float | None = None
        self.sla_config = LOADER_SLA_TARGETS.get(
            loader_name, (60 * 60, 180 * 60, 300 * 60)
        )  # Default: 1h expected, 3h warn, 5h critical

    def start(self) -> None:
        """Mark the start of loader execution."""
        self.start_time = time.time()
        logger.debug(f"[{self.loader_name}] SLA monitoring started")

    def get_status(self) -> SLAStatus:
        if self.start_time is None:
            return SLAStatus(
                loader_name=self.loader_name,
                elapsed_seconds=0,
                expected_seconds=self.sla_config[0],
                warning_threshold_seconds=self.sla_config[1],
                critical_threshold_seconds=self.sla_config[2],
                is_breaching=False,
                is_critical=False,
                margin_pct=100,
                recommendation="Not started",
            )

        elapsed = time.time() - self.start_time
        expected, warning, critical = self.sla_config

        is_critical = elapsed >= critical
        is_breaching = elapsed >= warning

        # Calculate margin as % of warning threshold
        margin = warning - elapsed
        if warning <= 0:
            logger.critical(
                f"[SLA_MONITOR CRITICAL] Warning threshold is {warning}. "
                f"Cannot calculate SLA margin without valid warning threshold."
            )
            raise RuntimeError(
                f"SLA monitoring failed: warning threshold is invalid ({warning}). "
                f"SLA configuration may be missing or corrupted."
            )
        margin_pct = max(0, (margin / warning * 100))

        recommendation = ""
        if is_critical:
            recommendation = (
                f"CRITICAL: Loader exceeded {critical / 60:.0f} min SLA. "
                f"Check for hung tasks, rate limiting, or database issues."
            )
        elif is_breaching:
            recommendation = (
                f"WARNING: Loader approaching {warning / 60:.0f} min limit. May not meet SLA if no improvement."
            )
        elif margin_pct < 50:
            recommendation = f"CAUTION: {margin_pct:.0f}% of warning threshold remaining. Monitor for slowdown."

        return SLAStatus(
            loader_name=self.loader_name,
            elapsed_seconds=elapsed,
            expected_seconds=expected,
            warning_threshold_seconds=warning,
            critical_threshold_seconds=critical,
            is_breaching=is_breaching,
            is_critical=is_critical,
            margin_pct=margin_pct,
            recommendation=recommendation,
        )

    def log_status(self, level: str = "debug") -> None:
        """Log current SLA status.

        Args:
            level: Log level ('debug', 'info', 'warning', 'error')
        """
        status = self.get_status()
        log_func = getattr(logger, level.lower())

        msg = (
            f"{status.status_emoji} [{status.status_text}] {self.loader_name}: "
            f"{status.elapsed_seconds / 60:.1f} min elapsed "
            f"({status.expected_seconds / 60:.0f} expected, "
            f"warn at {status.warning_threshold_seconds / 60:.0f} min)"
        )

        if status.recommendation:
            msg += f" | {status.recommendation}"

        log_func(msg)

    def publish_metric(self) -> None:
        """Publish SLA status as CloudWatch metric."""
        if MetricsPublisher is None:
            logger.warning("MetricsPublisher not available, skipping SLA metric publication")
            return

        try:
            status = self.get_status()
            metrics = MetricsPublisher()

            # Publish execution time metric
            metrics.add_metric(
                f"LoaderExecutionTime_{self.loader_name}",
                status.elapsed_seconds,
                unit="Seconds",
                dimensions={
                    "LoaderName": self.loader_name,
                    "SLAStatus": status.status_text,
                },
            )

            # Publish SLA compliance metric (1=compliant, 0=breaching)
            compliance = 0 if status.is_breaching else 1
            metrics.add_metric(
                f"LoaderSLACompliance_{self.loader_name}",
                compliance,
                unit="None",
                dimensions={
                    "LoaderName": self.loader_name,
                },
            )
        except Exception as e:
            logger.debug(f"Failed to publish SLA metrics: {e}")


class PipelineSLAMonitor:
    """Monitor entire pipeline execution times against SLA targets."""

    def __init__(self, pipeline_name: str):
        """Initialize pipeline SLA monitor.

        Args:
            pipeline_name: Name of the pipeline (e.g., 'morning_prep_pipeline')
        """
        self.pipeline_name = pipeline_name
        self.start_time: float | None = None

        # Require explicit SLA configuration - fail-fast on misconfigured pipeline names
        if pipeline_name not in PIPELINE_SLA_TARGETS:
            configured_pipelines = list(PIPELINE_SLA_TARGETS.keys())
            error_msg = (
                f"SLA config missing for pipeline {pipeline_name}, "
                f"check PIPELINE_SLA_TARGETS configuration. "
                f"Configured pipelines: {configured_pipelines}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        self.sla_config = PIPELINE_SLA_TARGETS[pipeline_name]

    def start(self) -> None:
        """Mark the start of pipeline execution."""
        self.start_time = time.time()
        logger.info(f"[PIPELINE] {self.pipeline_name} started, SLA budget: {self.sla_config[2] / 60:.0f} min")

    def get_status(self) -> SLAStatus:
        if self.start_time is None:
            return SLAStatus(
                loader_name=self.pipeline_name,
                elapsed_seconds=0,
                expected_seconds=self.sla_config[0],
                warning_threshold_seconds=self.sla_config[1],
                critical_threshold_seconds=self.sla_config[2],
                is_breaching=False,
                is_critical=False,
                margin_pct=100,
            )

        elapsed = time.time() - self.start_time
        expected, warning, critical = self.sla_config

        is_critical = elapsed >= critical
        is_breaching = elapsed >= warning
        margin_pct = max(0, ((critical - elapsed) / critical * 100)) if critical > 0 else 0

        return SLAStatus(
            loader_name=self.pipeline_name,
            elapsed_seconds=elapsed,
            expected_seconds=expected,
            warning_threshold_seconds=warning,
            critical_threshold_seconds=critical,
            is_breaching=is_breaching,
            is_critical=is_critical,
            margin_pct=margin_pct,
        )

    def check_and_alert(self) -> bool:
        status = self.get_status()

        if status.is_critical:
            logger.error(
                f"[PIPELINE] 🔴 {self.pipeline_name} CRITICAL: "
                f"{status.elapsed_seconds / 60:.0f} min elapsed (max {status.critical_threshold_seconds / 60:.0f} min)"
            )
            return False
        elif status.is_breaching:
            logger.warning(
                f"[PIPELINE] 🟡 {self.pipeline_name} WARNING: "
                f"{status.elapsed_seconds / 60:.0f} min elapsed (warn at {status.warning_threshold_seconds / 60:.0f} min)"
            )
            return False

        return True
