#!/usr/bin/env python3
"""Phase Registry - Declarative orchestrator phase definitions.

Centralizes all phase metadata, dependencies, and execution functions in one place.
Adding a new phase requires only adding one entry here, not modifying the orchestrator's
_setup_executor() method or adding new methods.

This design eliminates the Shotgun Surgery pattern where phase changes required
touching multiple methods in the Orchestrator class.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass

from algo.orchestrator.phase_result import PhaseResult

logger = logging.getLogger(__name__)


@dataclass
class PhaseRegistryEntry:
    """Declarative phase metadata with data contracts.

    This class defines how a phase executes in the orchestrator, including its
    dependencies, halt behavior, and function signature.

    Fields:
        phase_num: Unique phase identifier (1-9 typically)
        phase_name: Human-readable phase name for logs/reports
        dependencies: List of phase numbers this phase depends on (empty = no deps)
        execute_fn: Callable that executes the phase
            - Signature: execute_fn(**kwargs) -> PhaseResult
            - kwargs: executor (PhaseExecutor instance) passed by orchestrator
            - Returns: PhaseResult with status, summary, and result data
            - Contract: Must set PhaseResult.result['output_key'] with phase outputs
        skip_if_halted: If True, skip this phase if halt flag is set
        always_run: If True, always run this phase regardless of halt status

    Data Contract Specification:
        Input: PhaseExecutor instance with database access and configuration
        Output: PhaseResult(status, summary, result={...})
            - status: 'success', 'warning', 'error', or 'skipped'
            - summary: Human-readable operation summary
            - result: dict with phase-specific output data (see phase definitions below)
        Exceptions: RuntimeError, ValueError on critical failures; logged and caught
    """

    phase_num: int | str
    phase_name: str
    dependencies: list[int | str]
    execute_fn: Callable[..., PhaseResult] | None
    skip_if_halted: bool = True
    always_run: bool = False


class PhaseRegistry:
    """Registry of all orchestrator phases.

    Provides a single source of truth for phase definitions, enabling:
    - Dynamic phase discovery (query which phases exist)
    - Dependency validation (check what each phase needs)
    - Registration flexibility (add/remove phases at init time)
    - Testability (register test phases without modifying orchestrator)
    """

    # Phase definitions in execution order
    # Each entry declares: ID, name, dependencies, executor function, halt behavior
    # Data Contract: Input = database context, Output = PhaseResult with result={...}
    PHASES = [
        # Phase 1: DATA FRESHNESS CHECK
        # Input: Database with data_loader_status table
        # Output: result={'staleness_report': {...}} with table freshness status
        # Contract: All critical tables (buy_sell_daily, market_exposure_daily, etc.) must have data within SLA
        PhaseRegistryEntry(
            phase_num=1,
            phase_name="DATA FRESHNESS CHECK",
            dependencies=[],
            execute_fn=None,  # Will be set by orchestrator
            skip_if_halted=False,
        ),
        # Phase 2: CIRCUIT BREAKERS
        # Input: Market exposure data from Phase 1
        # Output: result={'halt_flag': bool, 'halt_reason': str} if circuit breaker triggered
        # Contract: May set halt_flag=True to stop entry execution if risk threshold exceeded
        PhaseRegistryEntry(
            phase_num=2,
            phase_name="CIRCUIT BREAKERS",
            dependencies=[1],
            execute_fn=None,
            skip_if_halted=False,
        ),
        # Phase 3: POSITION MONITOR
        # Input: Alpaca positions API data
        # Output: result={'positions': list, 'position_count': int, 'pnl_data': dict}
        # Contract: Syncs broker positions with local database, detects fills and partial fills
        PhaseRegistryEntry(
            phase_num=3,
            phase_name="POSITION MONITOR",
            dependencies=[],
            execute_fn=None,
            skip_if_halted=True,
        ),
        # Phase 4: RECONCILIATION
        # Input: Database positions from Phase 3, Alpaca position history
        # Output: result={'reconciliation_report': dict} with sync status
        # Contract: Verifies position state consistency between database and broker
        PhaseRegistryEntry(
            phase_num=4,
            phase_name="RECONCILIATION",
            dependencies=[3],
            execute_fn=None,
            skip_if_halted=True,
        ),
        # Phase 5: EXPOSURE POLICY ACTIONS
        # Input: Reconciliation results from Phase 4
        # Output: result={'exposure_actions': list} with exits to enforce limits
        # Contract: Generates forced exits if sector/stock exposure exceeds policy thresholds
        PhaseRegistryEntry(
            phase_num=5,
            phase_name="EXPOSURE POLICY ACTIONS",
            dependencies=[4],
            execute_fn=None,
            skip_if_halted=True,
        ),
        # Phase 6: EXIT EXECUTION
        # Input: Positions from Phase 3, exposure actions from Phase 5
        # Output: result={'exit_orders': list, 'exit_count': int} with executed orders
        # Contract: CRITICAL - Always runs regardless of halt (risk reduction must execute)
        # This allows position closure during market emergencies even when entries are blocked
        PhaseRegistryEntry(
            phase_num=6,
            phase_name="EXIT EXECUTION",
            dependencies=[3, 5],  # Depends on position monitor (Phase 3) AND exposure policy (Phase 5)
            execute_fn=None,
            skip_if_halted=False,  # CRITICAL: Exits ALWAYS run even when circuit breaker halts entries (risk management)
            always_run=True,  # Exits must execute to close positions during market emergencies
        ),
        # Phase 7: SIGNAL GENERATION & RANKING
        # Input: Market data, technical indicators, portfolio state from Phase 5
        # Output: result={'signals': list, 'qualified_trades': list} with ranked entry signals
        # Contract: Generates buy signals ranked by score; output per ranking criteria
        PhaseRegistryEntry(
            phase_num=7,
            phase_name="SIGNAL GENERATION & RANKING",
            dependencies=[5],
            execute_fn=None,
            skip_if_halted=True,
        ),
        # Phase 8: ENTRY EXECUTION
        # Input: Qualified signals from Phase 7, exposure policy from Phase 5
        # Output: result={'entry_orders': list, 'entry_count': int} with executed orders
        # Contract: Executes entry orders respecting position sizing and exposure limits
        PhaseRegistryEntry(
            phase_num=8,
            phase_name="ENTRY EXECUTION",
            dependencies=[7, 5],
            execute_fn=None,
            skip_if_halted=True,
        ),
        # Phase 9: RECONCILIATION & SNAPSHOT
        # Input: Trade orders from Phases 6 and 8, portfolio state
        # Output: result={'snapshot': {...}, 'metrics': {...}} with daily reconciliation
        # Contract: Creates portfolio_snapshots record with complete daily state; persists for analytics
        PhaseRegistryEntry(
            phase_num=9,
            phase_name="RECONCILIATION & SNAPSHOT",
            dependencies=[],  # always_run — no deps: runs even when Phase 8 was skipped (no signals)
            execute_fn=None,
            skip_if_halted=False,
            always_run=True,
        ),
    ]

    @classmethod
    def get_all_phases(cls) -> list[PhaseRegistryEntry]:
        """Get all registered phases in execution order.

        Returns:
            List of PhaseRegistryEntry objects in declared order
        """
        return cls.PHASES

    @classmethod
    def get_phase(cls, phase_num: int | str) -> PhaseRegistryEntry | None:
        """Look up a specific phase by number.

        Args:
            phase_num: Phase identifier to find

        Returns:
            PhaseRegistryEntry: if phase is registered
            None: if phase_num not found in registry (invalid phase number)
        """
        for phase in cls.PHASES:
            if phase.phase_num == phase_num:
                return phase
        logger.debug(f"Phase {phase_num} not found in registry")
        return None

    @classmethod
    def set_execute_fn(cls, phase_num: int | str, execute_fn: Callable[..., PhaseResult]) -> None:
        """Set the execution function for a phase.

        Called by orchestrator at init time to wire phase executors.
        This allows phase metadata to live in the registry while executors
        are methods on the Orchestrator.

        Args:
            phase_num: Phase to configure
            execute_fn: Callable that executes the phase

        Raises:
            ValueError: If phase_num not found
        """
        phase = cls.get_phase(phase_num)
        if phase is None:
            raise ValueError(f"Phase {phase_num} not found in registry")
        phase.execute_fn = execute_fn

    @classmethod
    def get_phase_dependencies(cls, phase_num: int | str) -> list[int | str]:
        """Get list of phases that must run before this phase.

        Args:
            phase_num: Phase to query

        Returns:
            List of required predecessor phase numbers (empty if no deps)

        Raises:
            ValueError: If phase_num not found in registry (indicates registration issue, not empty deps)
        """
        phase = cls.get_phase(phase_num)
        if phase is None:
            raise ValueError(
                f"Phase {phase_num} not registered in PhaseRegistry. "
                f"Available phases: {[p.phase_num for p in cls.PHASES]}. "
                f"Check: (1) Is phase defined in PHASES list? (2) Is phase_num correct? "
                f"(3) Was orchestrator initialization completed?"
            )
        return phase.dependencies

    @classmethod
    def get_phase_name(cls, phase_num: int | str) -> str:
        """Get human-readable name for a phase.

        Args:
            phase_num: Phase to query

        Returns:
            Phase name or "Unknown Phase N" if not found
        """
        phase = cls.get_phase(phase_num)
        return phase.phase_name if phase else f"Unknown Phase {phase_num}"
