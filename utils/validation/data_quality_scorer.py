#!/usr/bin/env python3
"""Data Quality Scorer - Consolidate quality metrics calculations."""

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class DataQualityScorer:

    @staticmethod
    def score_completeness(rows: list[dict[str, Any]], required_fields: set[str]) -> float:
        """Score data completeness (0-1)."""
        if not rows:
            return 0.0

        complete_count = 0
        for row in rows:
            if all(field in row and row[field] is not None for field in required_fields):
                complete_count += 1

        return complete_count / len(rows)

    @staticmethod
    def score_consistency(rows: list[dict[str, Any]]) -> float:
        """Score data consistency (0-1)."""
        if len(rows) < 2:
            return 1.0

        inconsistencies = 0
        for i in range(1, len(rows)):
            prev_keys = set(rows[i - 1].keys())
            curr_keys = set(rows[i].keys())
            if prev_keys != curr_keys:
                inconsistencies += 1

        return 1.0 - (inconsistencies / len(rows))

    @staticmethod
    def score_uniqueness(rows: list[dict[str, Any]], key_fields: list[str]) -> float:
        """Score data uniqueness via primary key violations (0-1)."""
        if not rows or not key_fields:
            return 1.0

        seen_keys: set[tuple[Any, ...]] = set()
        duplicates = 0

        for row in rows:
            key = tuple(row.get(field) for field in key_fields)
            if key in seen_keys:
                duplicates += 1
            else:
                seen_keys.add(key)

        return 1.0 - (duplicates / len(rows))

    @staticmethod
    def score_validity(rows: list[dict[str, Any]], validators: dict[str, Callable[..., Any]]) -> float:
        """Score data validity based on custom validators (0-1)."""
        if not rows or not validators:
            return 1.0

        invalid_count = 0
        for row in rows:
            for field, validator in validators.items():
                if field in row:
                    try:
                        if not validator(row[field]):
                            invalid_count += 1
                            break
                    except Exception as e:
                        logger.warning(f"Validator error for {field}: {e}")
                        invalid_count += 1
                        break

        return 1.0 - (invalid_count / len(rows))

    @classmethod
    def score_overall(
        cls,
        rows: list[dict[str, Any]],
        required_fields: set[str],
        key_fields: list[str],
        validators: dict[str, Callable[..., Any]] | None = None,
    ) -> dict[str, float]:
        """Calculate overall data quality score."""
        if validators is None:
            validators = {}

        completeness = cls.score_completeness(rows, required_fields)
        consistency = cls.score_consistency(rows)
        uniqueness = cls.score_uniqueness(rows, key_fields)
        validity = cls.score_validity(rows, validators)

        overall = (completeness + consistency + uniqueness + validity) / 4.0

        return {
            "overall": overall,
            "completeness": completeness,
            "consistency": consistency,
            "uniqueness": uniqueness,
            "validity": validity,
        }
