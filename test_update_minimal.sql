-- Minimal test: Update just risk_pct for TODAY only
BEGIN;

UPDATE buy_sell_daily
SET risk_pct = ROUND(
  CASE
    WHEN buylevel > 0 AND stoplevel IS NOT NULL THEN
      ((buylevel - stoplevel) / buylevel) * 100
    ELSE NULL
  END, 2)
WHERE date = CURRENT_DATE
  AND buylevel > 0;

SELECT 'Risk PCT Updated' as message, COUNT(*) as count FROM buy_sell_daily WHERE date = CURRENT_DATE AND risk_pct IS NOT NULL;

COMMIT;
