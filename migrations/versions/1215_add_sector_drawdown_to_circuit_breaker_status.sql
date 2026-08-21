-- Migration 1215: Add sector_drawdown_pct/worst_sector to circuit_breaker_status
--
-- Goal (2026-08-21, finance-accuracy audit): algo/risk/circuit_breaker.py's real
-- pretrade halt gate has enforced a sector-drawdown check (cost-basis-weighted
-- unrealized P&L per sector, halting at sector_drawdown_halt_pct e.g. -12%) since
-- commit f20b6e42a, but loaders/compute_circuit_breakers.py - the separate loader that
-- populates this table for the dashboard/Phase 9 alerting - never computed or stored
-- it. That loader's own docstring already warns its CB1-CB9 numbering is NOT the same
-- scheme as the real gate's (its own CB9 is win rate; the real gate's CB9 is sector
-- drawdown) - this migration/the accompanying code change adds sector drawdown as a
-- new, unnumbered metric rather than reusing either file's CB9 slot, to avoid deepening
-- that documented confusion.
--
-- Effect of the gap: if a sector-drawdown halt ever fired, an operator looking at this
-- table/the dashboard health panel would see nothing indicating why - only the generic
-- any_triggered/triggered_count flags, with no dedicated column revealing which sector
-- or by how much. The real halt enforcement was never affected (Phase 2 always used the
-- live gate directly, never this reporting table) - this is a visibility-only gap.

ALTER TABLE circuit_breaker_status ADD COLUMN IF NOT EXISTS sector_drawdown_pct NUMERIC;
ALTER TABLE circuit_breaker_status ADD COLUMN IF NOT EXISTS worst_sector_name VARCHAR(100);

COMMENT ON COLUMN circuit_breaker_status.sector_drawdown_pct IS
    'Cost-basis-weighted unrealized P&L percent of the worst-performing sector among open positions (negative = loss), mirroring algo/risk/circuit_breaker.py::_check_sector_drawdown. 0 when there are no open positions or all positions lack sector/P&L data to evaluate. NULL means not yet computed (pre-migration row).';
COMMENT ON COLUMN circuit_breaker_status.worst_sector_name IS
    'Sector name corresponding to sector_drawdown_pct. NULL when sector_drawdown_pct is 0 due to no open positions or missing data, or for pre-migration rows.';
