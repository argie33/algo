#!/usr/bin/env python3
"""Chunk Size Optimizer - Auto-tune chunk sizes based on memory constraints."""

import logging
import os

logger = logging.getLogger(__name__)


class ChunkSizeOptimizer:
    """Auto-tunes chunk_size based on available memory and ECS task limits."""

    def __init__(self, default_chunk_size: int = 10000) -> None:
        """Initialize optimizer with default chunk size."""
        self.default_chunk_size = default_chunk_size
        self.optimized_size = default_chunk_size

    def optimize(self) -> int:
        """Auto-tune chunk_size based on environment and memory.

        Priority:
        1. LOADER_CHUNK_SIZE env var (explicit override)
        2. Auto-tuned based on ECS_TASK_MEMORY_LIMIT
        3. Safe default based on memory availability

        Returns:
            Optimized chunk size
        """
        env_chunk_size = os.getenv("LOADER_CHUNK_SIZE")
        if env_chunk_size:
            try:
                configured = int(env_chunk_size)
                if 100 <= configured <= 100_000:
                    self.optimized_size = configured
                    logger.info(f"[CHUNK_SIZE] Using explicit config: {configured}")
                    return configured
            except ValueError:
                logger.warning(f"Invalid LOADER_CHUNK_SIZE: {env_chunk_size}, using auto-tuned")

        memory_limit_mb = int(os.getenv("ECS_TASK_MEMORY_LIMIT", "512"))
        safe_memory_mb = memory_limit_mb * 0.40
        avg_row_size_kb = 1.5
        safe_rows = int((safe_memory_mb * 1024) / avg_row_size_kb)
        optimized = max(2_000, min(50_000, safe_rows))

        self.optimized_size = optimized
        logger.info(
            f"[CHUNK_SIZE] Auto-tuned to {optimized} (memory={memory_limit_mb}MB, "
            f"safe={safe_memory_mb:.0f}MB, avg_row={avg_row_size_kb}KB)"
        )
        return optimized

    def get_chunk_size(self) -> int:
        """Get current optimized chunk size."""
        return self.optimized_size
