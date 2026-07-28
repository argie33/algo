-- Migration 1166: Add pending_exit_client_order_id to algo_trades for crash-safe exit idempotency
--
-- ISSUE: algo/trading/executor.py's _send_alpaca_exit() minted a fresh random UUID as
-- client_order_id on every call. Entries already use a deterministic idempotency_key so a
-- genuine retry of the same trade intent is deduped by Alpaca itself (see executor.py's
-- comment at the entry order submission site) - exits never had the equivalent protection.
-- If the process crashes between Alpaca confirming a fill and the enclosing DB transaction
-- committing, the position still looks untouched in the DB on the next cycle, and a retry
-- mints a brand-new unrelated client_order_id - Alpaca has no way to recognize it as a
-- duplicate. For a partial exit specifically (the remaining real shares genuinely cover a
-- duplicate order), this could silently double-sell part of the position.
--
-- FIX: persist the intended client_order_id BEFORE calling Alpaca, in its own immediately-
-- committed transaction independent of the caller's still-open transaction (so it survives
-- a crash even if that transaction later rolls back). A retry checks for an existing pending
-- id first and reuses it instead of minting a new one, so Alpaca's own idempotency protection
-- covers exits the same way it already covers entries. Cleared only on confirmed-success exit
-- recording (as part of the same transaction that records the exit), never on failure/timeout,
-- since an ambiguous outcome must keep the same id available for the next retry to reuse.

ALTER TABLE algo_trades ADD COLUMN IF NOT EXISTS pending_exit_client_order_id TEXT;

COMMENT ON COLUMN algo_trades.pending_exit_client_order_id IS
    'Set immediately before submitting an exit order to Alpaca (separate committed transaction, survives a crash of the main exit transaction); cleared only when the exit is confirmed and recorded. A retry reuses this value instead of minting a new client_order_id, so Alpaca dedupes a crash-recovery resubmission instead of executing it twice.';
