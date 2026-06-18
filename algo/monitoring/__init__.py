#!/usr/bin/env python3

from .connection_monitor import (
    check_stuck_connections,
    get_pool_status,
    on_connect,
    on_disconnect,
)
from .data_patrol import DataPatrol
from .pipeline_health import PipelineHealth
from .position_monitor import PositionMonitor


__all__ = [
    "get_pool_status",
    "check_stuck_connections",
    "on_connect",
    "on_disconnect",
    "PositionMonitor",
    "DataPatrol",
    "PipelineHealth",
]

# Wire pool tracking into the db module. utils.db cannot import us directly (circular dep),
# so we register the callbacks here once both modules are fully loaded.
from utils.db.connection import register_connection_callbacks


register_connection_callbacks(on_connect, on_disconnect)

