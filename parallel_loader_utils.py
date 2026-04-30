"""
Reusable utilities for parallel data loading across all loaders.
Ensures safe, consistent parallelization while preserving all data.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from typing import Callable, List, Dict, Any

logger = logging.getLogger(__name__)


def process_symbols_parallel(
    symbols: List[str],
    worker_function: Callable,
    worker_args: Dict[str, Any] = None,
    max_workers: int = 5,
    progress_interval: int = 100,
    process_name: str = "symbols"
) -> Dict[str, Any]:
    """
    Safely process a list of items in parallel with progress tracking.

    Args:
        symbols: List of items to process (e.g., stock symbols)
        worker_function: Callable that processes one item. Must return dict with:
            - "status": "success", "error", or "skip"
            - "item": the item identifier
            - other fields as needed
        worker_args: Dict of extra arguments to pass to worker_function
        max_workers: Number of parallel workers (default 5)
        progress_interval: How often to log progress (every N items)
        process_name: Display name for logging

    Returns:
        Dict with:
        - "completed": number of items completed
        - "successful": number of successful items
        - "errors": list of error items
        - "message": summary message

    Example:
        def fetch_symbol_data(symbol, api_key):
            try:
                data = fetch_api(symbol, api_key)
                insert_db(symbol, data)
                return {"status": "success", "item": symbol}
            except Exception as e:
                return {"status": "error", "item": symbol, "error": str(e)}

        result = process_symbols_parallel(
            symbols=symbols,
            worker_function=fetch_symbol_data,
            worker_args={"api_key": "123"},
            max_workers=5
        )
    """
    if not worker_args:
        worker_args = {}

    logger.info(f"Processing {len(symbols)} {process_name} in parallel with {max_workers} workers...")

    completed = 0
    successful = 0
    errors = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(worker_function, symbol, **worker_args): symbol
            for symbol in symbols
        }

        for future in as_completed(futures):
            try:
                result = future.result()
                completed += 1

                if result.get("status") == "success":
                    successful += 1
                elif result.get("status") == "error":
                    errors.append(result)

                if completed % progress_interval == 0:
                    logger.info(f"  ✓ {process_name}: {completed}/{len(symbols)} completed, {len(errors)} errors")

            except Exception as e:
                completed += 1
                errors.append({"item": symbols[completed - 1], "error": str(e)})
                logger.warning(f"  Worker error at {completed}/{len(symbols)}: {e}")

    summary = {
        "completed": completed,
        "successful": successful,
        "failed": len(errors),
        "message": f"Completed {successful}/{completed} {process_name} ({100*successful/completed:.1f}% success rate)"
    }

    logger.info(summary["message"])

    return summary


def batch_insert_rows(cursor, table_name: str, rows: List[tuple], batch_size: int = 100):
    """
    Insert rows in batches for efficiency.

    Args:
        cursor: Database cursor
        table_name: Target table
        rows: List of tuples to insert
        batch_size: Rows per batch (default 100)

    Returns:
        Number of rows inserted
    """
    from psycopg2.extras import execute_values

    inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        placeholders = ','.join(['%s'] * len(batch[0]))
        sql = f"INSERT INTO {table_name} VALUES " + ','.join([f'({placeholders})'] * len(batch))

        flat_data = [val for row in batch for val in row]
        execute_values(cursor, sql, batch)
        inserted += len(batch)

    return inserted


# Export for use in loaders
__all__ = ['process_symbols_parallel', 'batch_insert_rows']
