#!/usr/bin/env python3

from .connection_monitor import get_pool_status, check_stuck_connections, on_connect, on_disconnect

__all__ = [
    "get_pool_status",
    "check_stuck_connections",
    "on_connect",
    "on_disconnect",
    "PositionMonitor",
    "DataPatrol",
    "PipelineHealth",
]


def __getattr__(name: str):
    if name == "PositionMonitor":
        from .position_monitor import PositionMonitor
        return PositionMonitor
    if name == "DataPatrol":
        from .data_patrol import DataPatrol
        return DataPatrol
    if name == "PipelineHealth":
        from .pipeline_health import PipelineHealth
        return PipelineHealth
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
