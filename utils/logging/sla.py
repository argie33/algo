#!/usr/bin/env python3
"""SLA Monitoring — Tracks pipeline deadlines and provides alerts.

Monitors critical SLA windows:
- Morning Prep: 2:00 AM - 9:30 AM ET (7.5h budget)
- Afternoon Update: 12:50 PM - 1:05 PM ET (15m budget)
- Pre-Close Update: 2:50 PM - 3:15 PM ET (25m budget)
- EOD Pipeline: 4:05 PM - 5:30 PM ET (85m budget)
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

class SLAMonitor:
    """Track and log SLA compliance for critical pipelines."""

    EASTERN_TZ = ZoneInfo("America/New_York")

    # SLA windows: (start_hour, start_min, end_hour, end_min, pipeline_name, budget_minutes)
    SLA_WINDOWS = [
        (2, 0, 9, 30, "morning_prep", 450),  # 2:00 AM - 9:30 AM (7.5h = 450m)
        (12, 50, 13, 5, "afternoon_update", 15),  # 12:50 PM - 1:05 PM (15m)
        (14, 50, 15, 15, "preclose_update", 25),  # 2:50 PM - 3:15 PM (25m)
        (16, 5, 17, 30, "eod_pipeline", 85),  # 4:05 PM - 5:30 PM (85m)
    ]

    @classmethod
    def get_current_sla_window(cls) -> dict:
        """Get current SLA window if in one, None otherwise.

        Returns:
            {
                'name': 'morning_prep',
                'start_time': datetime,
                'end_time': datetime,
                'budget_minutes': 450,
                'elapsed_minutes': 45,
                'remaining_minutes': 405,
                'percent_complete': 10,
                'is_critical': False (True if >80% elapsed)
            }
            or None if not in any SLA window
        """
        now = datetime.now(cls.EASTERN_TZ)
        current_hour = now.hour
        current_min = now.minute
        current_time = current_hour * 60 + current_min

        for start_h, start_m, end_h, end_m, name, budget in cls.SLA_WINDOWS:
            start_time_minutes = start_h * 60 + start_m
            end_time_minutes = end_h * 60 + end_m

            if start_time_minutes <= current_time < end_time_minutes:
                start_dt = now.replace(
                    hour=start_h, minute=start_m, second=0, microsecond=0
                )
                end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

                # Handle overnight windows (EOD ends at 5:30 PM same day is fine)
                if end_h < start_h:
                    if current_hour < start_h:
                        start_dt = start_dt.replace(day=start_dt.day - 1)
                    else:
                        end_dt = end_dt.replace(day=end_dt.day + 1)

                elapsed_sec = (now - start_dt).total_seconds()
                elapsed_min = elapsed_sec / 60
                budget * 60
                remaining_min = budget - elapsed_min
                percent = (elapsed_min / budget) * 100

                return {
                    "name": name,
                    "start_time": start_dt,
                    "end_time": end_dt,
                    "budget_minutes": budget,
                    "elapsed_minutes": round(elapsed_min, 1),
                    "remaining_minutes": round(max(0, remaining_min), 1),
                    "percent_complete": round(percent, 1),
                    "is_critical": percent > 80,  # Flag if >80% of budget used
                }

        return None

    @classmethod
    def log_sla_status(cls, operation_name: str, elapsed_sec: float = None) -> dict:
        """Log current SLA status. Returns SLA info or None if not in window.

        Args:
            operation_name: Name of operation (for logging context)
            elapsed_sec: Time elapsed for this operation (optional)

        Returns:
            SLA window dict with status, or None if not in SLA window
        """
        sla = cls.get_current_sla_window()

        if not sla:
            logger.debug(f"[{operation_name}] Not in any SLA window")
            return None

        status = (
            "🔴 CRITICAL"
            if sla["is_critical"]
            else "🟡 WARNING" if sla["remaining_minutes"] < 10 else "🟢 OK"
        )

        elapsed_str = f", operation {elapsed_sec:.1f}s" if elapsed_sec else ""

        logger.info(
            f"[SLA-{sla['name'].upper()}] {status} "
            f"{sla['elapsed_minutes']:.0f}/{sla['budget_minutes']}m used ({sla['percent_complete']:.0f}%), "
            f"{sla['remaining_minutes']:.0f}m remaining{elapsed_str}"
        )

        return sla

    @classmethod
    def check_deadline_passed(cls, pipeline_name: str) -> bool:
        """Check if a pipeline deadline has passed (SLA failure).

        Args:
            pipeline_name: Name from SLA_WINDOWS (e.g., 'morning_prep')

        Returns:
            True if deadline passed, False otherwise
        """
        for start_h, start_m, end_h, end_m, name, budget in cls.SLA_WINDOWS:
            if name == pipeline_name:
                now = datetime.now(cls.EASTERN_TZ)
                end_dt = now.replace(hour=end_h, minute=end_m, second=0, microsecond=0)

                if end_h < start_h and now.hour >= 0 and now.hour < start_h:
                    # Handle overnight windows
                    end_dt = end_dt.replace(day=end_dt.day + 1)

                return now > end_dt

        return False

    @classmethod
    def warn_if_critical(cls, pipeline_name: str, operation_name: str):
        """Log warning if we're in critical SLA phase (>80% complete)."""
        sla = cls.get_current_sla_window()

        if sla and sla["name"] == pipeline_name and sla["is_critical"]:
            logger.warning(
                f"[CRITICAL-SLA] {pipeline_name} in critical phase: "
                f"{sla['remaining_minutes']:.0f}m remaining. "
                f"Must complete {operation_name} ASAP."
            )
            return True

        return False
