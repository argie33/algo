#!/usr/bin/env python3
"""Handler context — encapsulates dependencies for entry/exit handlers.

Extracted from TradeExecutor to decouple EntryHandler and ExitHandler from direct executor access.
Handlers receive a context object instead of the whole executor, reducing coupling and improving testability.
"""

from collections.abc import Callable
from decimal import Decimal
from typing import Any


class HandlerContext:
    """Context object providing dependencies for trade entry/exit handlers.

    Bundles:
    - Configuration and constants
    - Validation and TCA services
    - Callbacks to executor's private methods (needed for trade execution)
    - Public attributes (execution mode, etc.)
    """

    def __init__(
        self,
        config: Any,
        validator: Any,
        tca: Any,
        t1_target_r_multiple: float,
        t2_target_r_multiple: float,
        t3_target_r_multiple: float,
        execution_mode: str,
        # Callbacks to executor's private methods
        get_portfolio_value_fn: Callable[[], Decimal | None],
        with_cursor_fn: Callable[..., Any],
        validate_entry_conditions_fn: Callable[..., Any],
        submit_and_validate_order_fn: Callable[..., Any],
        cancel_bracket_orders_fn: Callable[..., Any],
        verify_order_status_fn: Callable[..., Any],
        get_order_filled_quantity_fn: Callable[..., Any],
        send_alpaca_exit_fn: Callable[..., Any],
        update_position_with_retry_fn: Callable[..., Any],
    ):
        """Initialize context with handler dependencies.

        Args:
            config: Algorithm configuration
            validator: TradeValidator instance
            tca: TCAEngine instance
            t1/t2/t3_target_r_multiple: R-multiple configuration
            execution_mode: Paper/review/auto execution mode
            *_fn: Callbacks to executor's private methods needed by handlers
        """
        # Configuration
        self.config = config
        self.execution_mode = execution_mode

        # Services
        self.validator = validator
        self.tca = tca

        # Constants
        self.t1_target_r_multiple = t1_target_r_multiple
        self.t2_target_r_multiple = t2_target_r_multiple
        self.t3_target_r_multiple = t3_target_r_multiple

        # Callbacks to executor's private methods
        # (These could be extracted into separate services in the future)
        self._get_portfolio_value = get_portfolio_value_fn
        self._with_cursor = with_cursor_fn
        self._validate_entry_conditions = validate_entry_conditions_fn
        self._submit_and_validate_order = submit_and_validate_order_fn
        self._cancel_bracket_orders = cancel_bracket_orders_fn
        self._verify_order_status = verify_order_status_fn
        self._get_order_filled_quantity = get_order_filled_quantity_fn
        self._send_alpaca_exit = send_alpaca_exit_fn
        self._update_position_with_retry = update_position_with_retry_fn
