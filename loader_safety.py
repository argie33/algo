#!/usr/bin/env python3
"""
Loader Safety Module - Prevent hanging, ensure proper timeouts
Wraps all Phase 2 loaders with safeguards
"""

import signal
import threading
import time
from contextlib import contextmanager
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import logging

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    """Raised when operation exceeds timeout"""
    pass


def timeout_handler(signum, frame):
    """Signal handler for timeout"""
    raise TimeoutException("Operation timed out")


@contextmanager
def timeout_context(seconds, message="Operation"):
    """Context manager for operation timeouts"""
    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    except TimeoutException:
        logger.error(f"{message} exceeded {seconds}s timeout - killing operation")
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def monitored_executor(max_workers=5, timeout_per_task=300, idle_timeout=120):
    """
    ThreadPoolExecutor wrapper with monitoring and timeout safeguards

    Args:
        max_workers: Max parallel threads
        timeout_per_task: Seconds per individual task before timeout
        idle_timeout: Seconds without progress before aborting
    """
    class MonitoredThreadPoolExecutor(ThreadPoolExecutor):
        def __init__(self, *args, **kwargs):
            super().__init__(max_workers=max_workers, *args, **kwargs)
            self.last_progress_time = time.time()
            self.progress_count = 0
            self.start_time = time.time()

        def submit_monitored(self, fn, *args, **kwargs):
            """Submit task with progress monitoring"""
            def wrapper(*args, **kwargs):
                self.last_progress_time = time.time()
                self.progress_count += 1
                try:
                    result = fn(*args, **kwargs)
                    return result
                except Exception as e:
                    logger.error(f"Task failed: {e}")
                    raise

            return self.submit(wrapper, *args, **kwargs)

        def wait_with_timeout(self, futures, task_name=""):
            """Wait for futures with timeout protection"""
            timeout_count = 0
            for i, future in enumerate(futures):
                try:
                    elapsed = time.time() - self.last_progress_time
                    if elapsed > idle_timeout:
                        logger.warning(f"No progress for {elapsed}s - task may be hung")
                        timeout_count += 1

                    # Wait with timeout
                    future.result(timeout=timeout_per_task)

                except FuturesTimeoutError:
                    timeout_count += 1
                    logger.error(f"Task {i} timed out after {timeout_per_task}s")
                    if timeout_count > 3:  # Abort after 3 timeouts
                        logger.error(f"Too many timeouts ({timeout_count}) - aborting loader")
                        self.shutdown(wait=False)
                        raise TimeoutException(f"{task_name} exceeded timeout limits")

                # Progress update
                if i % max(1, len(futures) // 10) == 0:
                    logger.info(f"{task_name} progress: {i}/{len(futures)}")

    return MonitoredThreadPoolExecutor()


class LoaderSafety:
    """Wrapper to add safety checks to any loader"""

    def __init__(self, loader_name, max_duration=1800):
        """
        Args:
            loader_name: Name of loader (e.g., 'loadsectors')
            max_duration: Max seconds the loader can run (default 30 min)
        """
        self.loader_name = loader_name
        self.max_duration = max_duration
        self.start_time = None
        self.last_heartbeat = None

    def __enter__(self):
        self.start_time = time.time()
        self.last_heartbeat = time.time()
        logger.info(f"[{self.loader_name}] Starting with {self.max_duration}s timeout")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = time.time() - self.start_time
        logger.info(f"[{self.loader_name}] Completed in {elapsed:.1f}s")

        if elapsed > self.max_duration:
            logger.error(f"[{self.loader_name}] EXCEEDED max duration {self.max_duration}s")
            return False

        return False

    def heartbeat(self, message=""):
        """Record progress to detect hanging"""
        now = time.time()
        elapsed_since_heartbeat = now - self.last_heartbeat
        total_elapsed = now - self.start_time

        if elapsed_since_heartbeat > 60:
            logger.warning(f"[{self.loader_name}] No heartbeat for {elapsed_since_heartbeat:.1f}s")

        if total_elapsed > self.max_duration:
            raise TimeoutException(f"[{self.loader_name}] Exceeded max duration")

        self.last_heartbeat = now
        if message:
            logger.debug(f"[{self.loader_name}] {message}")


def safe_batch_insert(conn, query, data, batch_size=1000, loader_name=""):
    """
    Safe batch insert with timeout protection

    Args:
        conn: Database connection
        query: SQL query with %s placeholders
        data: List of tuples to insert
        batch_size: Rows per batch
        loader_name: For logging
    """
    if not data:
        logger.warning(f"[{loader_name}] No data to insert")
        return 0

    total_inserted = 0
    batches = [data[i:i+batch_size] for i in range(0, len(data), batch_size)]

    try:
        with LoaderSafety(f"{loader_name}_insert", max_duration=300) as safety:
            cursor = conn.cursor()

            for i, batch in enumerate(batches):
                try:
                    from psycopg2.extras import execute_values
                    execute_values(
                        cursor,
                        query,
                        batch,
                        page_size=batch_size
                    )
                    conn.commit()
                    total_inserted += len(batch)
                    safety.heartbeat(f"Inserted {total_inserted}/{len(data)} rows")

                except Exception as e:
                    logger.error(f"Batch {i} insert failed: {e}")
                    conn.rollback()
                    raise

            cursor.close()

    except TimeoutException as e:
        logger.error(f"Insert timed out: {e}")
        raise

    logger.info(f"[{loader_name}] Inserted {total_inserted} rows")
    return total_inserted


# Configuration for each loader
LOADER_CONFIGS = {
    'loadsectors': {
        'max_duration': 600,  # 10 minutes
        'max_workers': 5,
        'task_timeout': 180,  # 3 minutes per task
        'idle_timeout': 120,  # 2 minutes idle
    },
    'loadecondata': {
        'max_duration': 900,  # 15 minutes
        'max_workers': 3,
        'task_timeout': 300,  # 5 minutes per task
        'idle_timeout': 180,  # 3 minutes idle
    },
    'loadstockscores': {
        'max_duration': 1200,  # 20 minutes
        'max_workers': 5,
        'task_timeout': 300,  # 5 minutes per task
        'idle_timeout': 180,  # 3 minutes idle
    },
    'loadfactormetrics': {
        'max_duration': 1200,  # 20 minutes
        'max_workers': 5,
        'task_timeout': 300,  # 5 minutes per task
        'idle_timeout': 180,  # 3 minutes idle
    },
}


def get_loader_config(loader_name):
    """Get safety config for a loader"""
    return LOADER_CONFIGS.get(loader_name, LOADER_CONFIGS['loadsectors'])


if __name__ == "__main__":
    # Test timeouts
    print("Loader Safety Module Loaded")
    print(f"Configurations: {list(LOADER_CONFIGS.keys())}")
