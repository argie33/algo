# Real-Money Go-Live Checklist

Result of a from-scratch, skeptical independent audit (2026-09-08) of financial calculation
integrity, order execution, pretrade risk gates, and stop-loss protection — done specifically
to verify (not assume from memory/comments) that the algo is ready to trade real money.

## VERIFIED CLEAN (code-level, independently re-derived — not taken on faith)

- **Financial calculations**: ROE/ROIC/D-E/PEG/FCF-margin/margins all match standard finance
  definitions. Every ratio has zero/negative-denominator guards that produce a distinct
  semantic state (e.g. `roic_pct_negative_invested_capital`) instead of a garbage extreme
  value. VaR uses empirical historical simulation (not naive parametric-normal — avoids the
  fat-tail/wrong-z-score failure mode) and portfolio VaR comes from the real historical
  equity series (embeds actual correlation, not a naive sum of position VaRs). Position
  sizing matches the standard fixed-fractional risk formula exactly, Decimal-based
  throughout (no float drift). Sharpe/Sortino/Calmar all correctly annualized.
- **Order execution**: Entries are always real broker-side GTC bracket orders (limit entry +
  stop-loss leg) — never a software-only stop that depends on the bot staying alive. Exits
  correctly use day+market or a properly-directioned slippage-buffered limit. Idempotent,
  deterministic `client_order_id`, with genuine ground-truth reconciliation against the
  broker before ever retrying an ambiguous (timeout/network-error) submission — the exact
  case that causes accidental double-orders in naive systems.
- **Pretrade risk gates**: Sizing, portfolio-heat (aggregate open risk, not just per-trade),
  sector-concentration, PDT, and buying-power checks are all real hard blocks wired into the
  live entry path (not just logging), and all fail CLOSED on error (DB timeout, missing
  data, etc. blocks the trade rather than letting it through). Migration 1158's unique DB
  index (the actual duplicate-entry race guard) is confirmed live in the schema.
- **Stop-loss logic**: Trailing-stop math only tightens (never loosens), correctly clamped
  below current price. Pyramided/multi-lot positions are each covered by their own
  correctly-sized stop. Manual flatten-all kill switch correctly cancels/replaces
  everything, cross-checked against live broker state (not just local DB).

## ONE OPEN ITEM — requires action in AWS, deliberately NOT done during this audit

**Stop-loss leg liveness repair currently only runs 5x/day** (as part of the full Phase 9
orchestrator cycle), not continuously. If a resting stop-loss order gets cancelled or
desynced at the broker between orchestrator runs (day-TIF expiry, broker-side glitch, manual
intervention), the position can sit unprotected for up to several hours during market hours.

**The fix is already fully built and committed to `main`** — nothing left to implement:
- `terraform/modules/services/stop-loss-guardian.tf` — a dedicated 15-minute intraday-only
  stop-leg verify/repair schedule, reusing the already-deployed orchestrator Lambda (no new
  function/IAM role needed).
- `terraform/prod.tfvars:78` already has `enable_stop_loss_guardian = true` set.

**What's actually missing**: nobody has run the deploy that applies this to AWS.
`deploy-all-infrastructure.yml` is manual-only by design (`workflow_dispatch`) — it does
NOT auto-apply on every merge to main (that auto-apply behavior was itself a bug, fixed
2026-09-06, specifically to prevent unreviewed production changes).

**Before trading real money, when you're ready to work in AWS:**
```bash
gh workflow run deploy-all-infrastructure.yml
```
or trigger "Deploy All Infrastructure (Terraform)" manually from the GitHub Actions tab.
This is a real, ~10-15 minute production deploy (rebuilds/redeploys all Lambdas + a broad
`terraform apply`) — review the plan output before/as it runs. Until this runs, the algo is
safe to test/paper-trade locally, but the intraday stop-repair gap above stays open for
real-money live trading.

## Design decisions intentionally NOT flagged as gaps (verified, not bugs)

- TCA (transaction cost analysis) is descriptive-only, not fed back into execution decisions
  (limit price width, order type choice). Not a safety issue — a future execution-quality
  improvement, not required before going live.
- `unified-risk-monitor` (a more aggressive 5-min auto-halt/auto-flatten consolidation) was
  a separate, broader feature under consideration — track its status separately; it is not
  required to close the stop-loss gap above, which stop-loss-guardian closes on its own.
