#!/usr/bin/env python3

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PhaseResult:
    """Standardized result envelope every orchestrator phase returns."""

    phase_num: int | str
    phase_name: str
    status: str  # 'ok' | 'halted' | 'degraded' | 'skipped'
    data: dict[str, Any] = field(default_factory=dict)
    halted: bool = False
    error: str | None = None
    dependencies: list[int | str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Returns True if phase completed successfully."""
        return self.status == "ok"


@dataclass
class Phase1Result(PhaseResult):
    """Phase 1: Data Freshness Check."""

    def __init__(self, status: str, **kwargs):
        super().__init__(
            phase_num=1,
            phase_name="DATA FRESHNESS CHECK",
            status=status,
            dependencies=[],
            **kwargs,
        )


@dataclass
class Phase2Result(PhaseResult):
    """Phase 2: Circuit Breakers.

    Depends on: Phase 1
    """

    def __init__(self, status: str, **kwargs):
        super().__init__(
            phase_num=2,
            phase_name="CIRCUIT BREAKERS",
            status=status,
            dependencies=[1],
            **kwargs,
        )


@dataclass
class Phase3Result(PhaseResult):
    """Phase 3: Position Monitor.

    Runs independently to review positions regardless of Phase 2 outcome.
    Produces: position recommendations
    """

    def __init__(self, status: str, recommendations: list[dict] | None = None, **kwargs):
        super().__init__(
            phase_num=3,
            phase_name="POSITION MONITOR",
            status=status,
            dependencies=[],
            data={"recommendations": recommendations if recommendations is not None else []},
            **kwargs,
        )


@dataclass
class Phase4Result(PhaseResult):
    """Phase 4: Reconciliation (lightweight).

    Depends on: Phase 3
    """

    def __init__(self, status: str, **kwargs):
        super().__init__(
            phase_num=4,
            phase_name="RECONCILIATION",
            status=status,
            dependencies=[3],
            **kwargs,
        )


@dataclass
class Phase5Result(PhaseResult):
    """Phase 5: Exposure Policy Actions.

    Depends on: Phase 4
    Produces: constraints, actions
    """

    def __init__(
        self,
        status: str,
        constraints: dict | None = None,
        actions: list[dict] | None = None,
        **kwargs,
    ):
        super().__init__(
            phase_num=5,
            phase_name="EXPOSURE POLICY ACTIONS",
            status=status,
            dependencies=[4],
            data={
                "constraints": constraints if constraints is not None else {},
                "actions": actions if actions is not None else [],
            },
            **kwargs,
        )


@dataclass
class Phase6Result(PhaseResult):
    """Phase 6: Exit Execution.

    Depends on: Phase 5
    Produces: exit summary
    """

    def __init__(self, status: str, exits_executed: int = 0, **kwargs):
        super().__init__(
            phase_num=6,
            phase_name="EXIT EXECUTION",
            status=status,
            dependencies=[5],
            data={"exits_executed": exits_executed},
            **kwargs,
        )


@dataclass
class Phase7Result(PhaseResult):
    """Phase 7: Signal Generation & Ranking.

    Depends on: Phase 5 (for exposure_constraints)
    Produces: qualified_trades
    """

    def __init__(self, status: str, qualified_trades: list[dict] | None = None, **kwargs):
        super().__init__(
            phase_num=7,
            phase_name="SIGNAL GENERATION & RANKING",
            status=status,
            dependencies=[5],
            data={"qualified_trades": qualified_trades if qualified_trades is not None else []},
            **kwargs,
        )


@dataclass
class Phase8Result(PhaseResult):
    """Phase 8: Entry Execution.

    Depends on: Phase 7 (for qualified_trades), Phase 5 (for exposure_constraints)
    Produces: entry summary
    """

    def __init__(self, status: str, entered: int = 0, **kwargs):
        super().__init__(
            phase_num=8,
            phase_name="ENTRY EXECUTION",
            status=status,
            dependencies=[7, 5],
            data={"entered": entered},
            **kwargs,
        )


@dataclass
class Phase9Result(PhaseResult):
    """Phase 9: Reconciliation & Snapshot.

    Depends on: All prior phases (for snapshot finality)
    Produces: portfolio snapshot
    """

    def __init__(self, status: str, positions: int = 0, **kwargs):
        super().__init__(
            phase_num=9,
            phase_name="RECONCILIATION & SNAPSHOT",
            status=status,
            dependencies=[],
            data={"positions": positions},
            **kwargs,
        )
