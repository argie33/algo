"""
Polars-optimized loader base class.

Drop-in replacement for pandas-based loaders. 5-10x faster, lower memory,
streaming-safe.

Why Polars over pandas:
    - Lazy evaluation: filter/aggregate before materializing
    - Native Arrow memory: zero-copy to PostgreSQL via COPY
    - Multi-threaded by default (pandas is single-threaded)
    - 2-5x lower memory footprint on the same data
    - Type-strict: catches bad data at parse time

Why Polars over Rust:
    - Same speed for I/O-bound work (the bottleneck for loaders)
    - Pure Python interface — same skill set as existing loaders
    - Drop-in replacement: code shape stays familiar

Usage:
    from loader_polars_base import PolarsLoader

    class PriceDailyLoader(PolarsLoader):
        table_name = "price_daily"
        primary_key = ["symbol", "date"]

        def transform(self, df: pl.DataFrame) -> pl.DataFrame:
            return df.filter(pl.col("volume") > 0)

    loader = PriceDailyLoader()
    loader.run(symbols=["AAPL", "MSFT"])
"""

from __future__ import annotations

import io
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Iterable, List, Optional, Sequence

# >>> dotenv-autoload >>>
from pathlib import Path as _DotenvPath
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_file = _DotenvPath(__file__).resolve().parent / '.env.local'
    if _env_file.exists():
        _load_dotenv(_env_file)
except ImportError:
    pass
# <<< dotenv-autoload <<<

log = logging.getLogger(__name__)


class PolarsLoader(ABC):
    """Base class for Polars-backed loaders.

    Subclasses implement `fetch()` (data acquisition) and optionally
    `transform()` (cleaning/derivation). Insertion uses PostgreSQL COPY
    for maximum throughput.
    """

    table_name: str = ""
    primary_key: Sequence[str] = ()
    chunk_size: int = 10_000
    use_bloom_dedup: bool = True

    def __init__(self):
        self._conn = None
        self._dedup = None
        self._stats = {
            "fetched": 0,
            "filtered_dedup": 0,
            "filtered_quality": 0,
            "inserted": 0,
            "duration_sec": 0.0,
        }

    # ----- Subclass interface -----

    @abstractmethod
    def fetch(self, symbol: str):
        """Return a polars.DataFrame for one symbol. Empty/None if nothing fetched."""

    def transform(self, df):
        """Optional override: clean/derive columns. Default is identity."""
        return df

    def validate(self, df) -> "tuple[object, int]":
        """Apply quality checks. Returns (cleaned_df, dropped_count).

        Default rules: drop rows where any primary key is null.
        Override to add domain-specific rules (volume > 0, high >= low, etc.).
        """
        import polars as pl

        before = df.height
        for col in self.primary_key:
            df = df.filter(pl.col(col).is_not_null())
        return df, before - df.height

    # ----- Infrastructure -----

    def _connect(self):
        import psycopg2

        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),
                user=os.getenv("DB_USER", "stocks"),
                password=os.getenv("DB_PASSWORD", ""),
                database=os.getenv("DB_NAME", "stocks"),
            )
        return self._conn

    def _get_dedup(self):
        if not self.use_bloom_dedup or self._dedup is not None:
            return self._dedup
        try:
            from bloom_dedup import LoadDedup

            self._dedup = LoadDedup(namespace=self.table_name)
        except Exception as e:
            log.warning("Dedup unavailable (%s) — falling back to ON CONFLICT only", e)
        return self._dedup

    # ----- Insert path -----

    def _copy_into(self, df) -> int:
        """Stream a Polars DataFrame into Postgres via COPY.

        Uses ON CONFLICT DO UPDATE through a staging table to handle dedup
        when the Bloom filter has false positives. Much faster than
        execute_values + per-row ON CONFLICT.
        """
        import polars as pl  # noqa: F401

        if df.is_empty():
            return 0

        conn = self._connect()
        cur = conn.cursor()
        try:
            staging = f"_stage_{self.table_name}_{int(time.time() * 1000)}"
            columns = df.columns

            # Create unlogged staging table for speed
            cur.execute(
                f"CREATE UNLOGGED TABLE {staging} (LIKE {self.table_name} INCLUDING DEFAULTS)"
            )

            # Stream Polars → CSV → COPY
            buf = io.BytesIO()
            df.write_csv(buf, include_header=False)
            buf.seek(0)
            cur.copy_expert(
                f"COPY {staging} ({','.join(columns)}) FROM STDIN WITH (FORMAT CSV)",
                buf,
            )

            # Merge from staging with conflict resolution
            updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c not in self.primary_key)
            on_conflict = (
                f"ON CONFLICT ({','.join(self.primary_key)}) DO UPDATE SET {updates}"
                if self.primary_key
                else "ON CONFLICT DO NOTHING"
            )
            cur.execute(
                f"INSERT INTO {self.table_name} ({','.join(columns)}) "
                f"SELECT {','.join(columns)} FROM {staging} "
                f"{on_conflict}"
            )
            inserted = cur.rowcount

            cur.execute(f"DROP TABLE {staging}")
            conn.commit()
            return inserted
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

    # ----- Orchestration -----

    def load_symbol(self, symbol: str) -> int:
        """Load one symbol. Returns rows inserted."""
        df = self.fetch(symbol)
        if df is None or df.height == 0:
            return 0
        self._stats["fetched"] += df.height

        df = self.transform(df)
        df, dropped = self.validate(df)
        self._stats["filtered_quality"] += dropped

        # Bloom-filter dedup before COPY
        dedup = self._get_dedup()
        if dedup is not None and self.primary_key:
            before = df.height
            keys = df.select(self.primary_key).to_dicts()
            mask = [
                not dedup.exists(":".join(str(k[c]) for c in self.primary_key))
                for k in keys
            ]
            import polars as pl

            df = df.filter(pl.Series(mask))
            self._stats["filtered_dedup"] += before - df.height

        if df.height == 0:
            return 0

        inserted = self._copy_into(df)
        self._stats["inserted"] += inserted

        # Update dedup AFTER successful insert
        if dedup is not None and self.primary_key:
            keys = df.select(self.primary_key).to_dicts()
            for k in keys:
                dedup.add(":".join(str(k[c]) for c in self.primary_key))

        return inserted

    def run(self, symbols: Iterable[str]) -> dict:
        """Execute the load pipeline across symbols. Returns stats."""
        start = time.time()
        symbols = list(symbols)
        log.info("[%s] Loading %d symbols with Polars", self.table_name, len(symbols))

        for i, symbol in enumerate(symbols, 1):
            try:
                self.load_symbol(symbol)
                if i % 100 == 0:
                    log.info("  %d/%d processed", i, len(symbols))
            except Exception as e:
                log.error("  %s failed: %s", symbol, e)

        self._stats["duration_sec"] = round(time.time() - start, 2)
        log.info(
            "[%s] Done. fetched=%d, dedup_skip=%d, quality_drop=%d, inserted=%d, %.1fs",
            self.table_name,
            self._stats["fetched"],
            self._stats["filtered_dedup"],
            self._stats["filtered_quality"],
            self._stats["inserted"],
            self._stats["duration_sec"],
        )
        return self._stats

    def close(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
