-- Migration 1175: Add max drawdown metric to stability_metrics
-- Adds max_drawdown_1y and reason tracking for peak-to-trough decline calculations

BEGIN;

-- Add max drawdown column and unavailability reason
ALTER TABLE stability_metrics
ADD COLUMN IF NOT EXISTS max_drawdown_1y NUMERIC(6, 2) NULL,
ADD COLUMN IF NOT EXISTS max_drawdown_1y_unavailable_reason VARCHAR(255) NULL;

COMMIT;
