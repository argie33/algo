-- Migration 1257: Track a standalone protective stop order placed by auto-remediation
--
-- CONTEXT: Phase 9's stop-loss protection check (phase9_reconciliation.py's
-- _verify_open_position_stop_loss_protection_step) previously only detected a missing
-- bracket stop-loss leg and alerted a human to re-arm it manually. Auto-remediation now
-- submits a standalone protective stop order directly (not as a leg of the original
-- bracket) when a gap is found. That standalone order has no relationship to the
-- original bracket's alpaca_order_id, so check_stop_loss_leg_live (which only inspects
-- the ORIGINAL bracket's legs) would keep reporting "missing" forever and cause the
-- remediation step to resubmit a duplicate protective stop every single cycle.
--
-- This column lets the check step look for an already-placed standalone repair order
-- before attempting another one.

ALTER TABLE algo_positions ADD COLUMN IF NOT EXISTS standalone_stop_order_id TEXT;
