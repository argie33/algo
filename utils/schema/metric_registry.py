#!/usr/bin/env python3
"""Metric Registry - Single source of truth for stock metric definitions.

Solves Shotgun Surgery for adding metrics: Instead of changing 6+ files
(migration, loader, schema, API, dashboard, config), all metric definitions
are registered in ONE place. Each system pulls configuration from here.

When adding a new metric like 'price_momentum':
1. Register it here with column name, type, description
2. Loader code automatically knows column type + validation rules
3. API handler automatically exposes it in responses
4. Dashboard automatically includes it in charts
5. Config automatically includes it in thresholds

This eliminates the "10+ files touched" problem by making the metric
definition the single source of truth.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any


class MetricType(Enum):
    """Supported metric data types in database."""

    NUMERIC = "numeric"
    INTEGER = "integer"
    VARCHAR = "varchar"
    DATE = "date"
    BOOLEAN = "boolean"


class MetricCategory(Enum):
    """Business category for metric."""

    PRICE = "price"
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    RISK = "risk"
    MARKET = "market"
    MOMENTUM = "momentum"


@dataclass
class MetricDefinition:
    """Complete metric definition - single source of truth.

    When adding a new metric, define it once here. All systems
    (loaders, APIs, dashboard, config) reference this definition.
    """

    # Unique identifier
    name: str

    # Database column definition
    column_name: str
    data_type: MetricType

    # Business metadata
    category: MetricCategory
    description: str
    nullable: bool = False
    default_value: Any | None = None
    unit: str | None = None  # e.g., "%" for percentages

    # Validation rules (used by loaders)
    min_value: float | None = None
    max_value: float | None = None
    validator_func: Callable[[Any], bool] | None = None

    # Dashboard/API display rules
    display_name: str = ""
    display_precision: int = 2
    is_percentage: bool = False
    is_ranking: bool = False

    # Config thresholds (used by orchestration/risk)
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    trend_direction: str | None = None  # "higher_is_better" or "lower_is_better"

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name.replace("_", " ").title()

    def get_column_definition(self) -> str:
        """Generate SQL column definition for migrations."""
        type_map = {
            MetricType.NUMERIC: "NUMERIC(10,2)",
            MetricType.INTEGER: "INTEGER",
            MetricType.VARCHAR: "VARCHAR(255)",
            MetricType.DATE: "DATE",
            MetricType.BOOLEAN: "BOOLEAN",
        }
        sql_type = type_map[self.data_type]
        null_clause = "" if self.nullable else " NOT NULL"
        default_clause = f" DEFAULT {self.default_value}" if self.default_value else ""
        return f"{self.column_name} {sql_type}{null_clause}{default_clause}"

    def validate(self, value: Any) -> bool:
        """Validate value against metric rules."""
        if value is None:
            return self.nullable

        # Custom validator
        if self.validator_func:
            return self.validator_func(value)

        # Range validation
        if self.min_value is not None and value < self.min_value:
            return False
        if self.max_value is not None and value > self.max_value:
            return False

        return True


class MetricRegistry:
    """Registry of all metrics in the system.

    Single source of truth that all systems reference.
    """

    # Stock-level metrics
    STOCK_METRICS = {
        "composite_score": MetricDefinition(
            name="composite_score",
            column_name="composite_score",
            data_type=MetricType.NUMERIC,
            category=MetricCategory.TECHNICAL,
            description="Composite technical score (0-100)",
            min_value=0.0,
            max_value=100.0,
            warning_threshold=30.0,
            critical_threshold=20.0,
            trend_direction="higher_is_better",
            is_ranking=True,
        ),
        "momentum_score": MetricDefinition(
            name="momentum_score",
            column_name="momentum_score",
            data_type=MetricType.NUMERIC,
            category=MetricCategory.MOMENTUM,
            description="Price momentum score",
            unit="%",
            is_percentage=True,
        ),
        "dividend_yield": MetricDefinition(
            name="dividend_yield",
            column_name="dividend_yield",
            data_type=MetricType.NUMERIC,
            category=MetricCategory.FUNDAMENTAL,
            description="Annual dividend yield",
            unit="%",
            min_value=0.0,
            is_percentage=True,
        ),
    }

    # Market-level metrics
    MARKET_METRICS = {
        "vix_level": MetricDefinition(
            name="vix_level",
            column_name="vix_level",
            data_type=MetricType.NUMERIC,
            category=MetricCategory.MARKET,
            description="CBOE Volatility Index",
            min_value=0.0,
            warning_threshold=25.0,
            critical_threshold=35.0,
            trend_direction="lower_is_better",
        ),
        "market_stage": MetricDefinition(
            name="market_stage",
            column_name="market_stage",
            data_type=MetricType.INTEGER,
            category=MetricCategory.MARKET,
            description="Market stage (1-4)",
            min_value=1,
            max_value=4,
            is_ranking=True,
        ),
    }

    @classmethod
    def get_metric(cls, name: str) -> MetricDefinition | None:
        metric = cls.STOCK_METRICS.get(name)
        if metric is None:
            metric = cls.MARKET_METRICS.get(name)
        return metric

    @classmethod
    def get_all_metrics(cls) -> dict[str, MetricDefinition]:
        return {**cls.STOCK_METRICS, **cls.MARKET_METRICS}

    @classmethod
    def get_metrics_by_category(cls, category: MetricCategory) -> dict[str, MetricDefinition]:
        all_metrics = cls.get_all_metrics()
        return {k: v for k, v in all_metrics.items() if v.category == category}


# Example: When you need to add a new metric, just register it here:
# Example registration (commented out):
# NEW_METRIC = MetricDefinition(
#     name="price_momentum",
#     column_name="price_momentum",
#     data_type=MetricType.NUMERIC,
#     category=MetricCategory.MOMENTUM,
#     description="30-day price momentum indicator",
#     min_value=-100.0,
#     max_value=100.0,
#     warning_threshold=-20.0,
#     critical_threshold=-50.0,
#     trend_direction="higher_is_better",
#     is_percentage=True,
# )
# MetricRegistry.STOCK_METRICS["price_momentum"] = NEW_METRIC
