"""Transient error types for loader retry logic.

These exceptions signal temporary failures that should trigger retries with backoff,
as opposed to permanent data unavailability or programming errors.
"""


class TransientAPIError(Exception):
    """Raised for transient API failures (timeouts, connection errors) that should trigger retries.

    When a loader encounters a transient error (e.g., API timeout during high market volatility),
    the orchestrator will automatically retry with exponential backoff. This is distinct from
    legitimate data unavailability (e.g., a stock having no analyst coverage).

    Finance principle: Missing data (transient) != No data (permanent). Retry is appropriate
    for the former; skip is appropriate for the latter.
    """
