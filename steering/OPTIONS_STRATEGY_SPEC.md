# Options Sleeve Strategy Spec (Phase 2)

Status: **DRAFT — not yet approved for phase 3 (backtest) to build against.** This is phase 2
of the 7-phase options-strategy plan (see `MEMORY.md`
`options_strategy_full_plan_and_phase1_20260912`). Phase 1 (real scheduled data) is done
(`9948e2ca2`). Nothing here authorizes placing a real order — that is gated separately by
phases 3-6 below and by this doc's own go/no-go criteria.

Written because the existing options screener (`dashboard/panels/options.py`,
`lambda/api/routes/options.py`) is explicitly a **screener, not a strategy** — it has no
concept of position sizing, capital allocation, assignment handling, or exit rules. Treating
it as tradeable today would mean sizing real option sales with no written risk budget, which
is how a "small pilot" quietly becomes an uncapped exposure. This doc exists to close that
gap before any execution code gets written.

## 0. Why a percentage-of-equity cap, not a fixed dollar figure

A fixed dollar cap (e.g. "$10,000") either becomes meaningless as the account grows or
over-constrains a smaller account — and it requires re-deciding by hand every time equity
moves materially, which is exactly the kind of manual step that gets forgotten. Every sizing
control that already exists in this codebase (`PositionSizer`, `max_positions_per_sector`,
portfolio-heat checks in `algo/orchestrator/phase2_circuit_breakers.py`) is percentage-of-
equity-based for the same reason. The options sleeve follows the same convention:

**Sleeve capital cap = 5% of total account equity**, hard-enforced (not advisory), recomputed
from live Alpaca account equity at the top of every phase that touches the sleeve — never a
number cached at strategy-design time. Rationale for 5% specifically, standard
options-income-strategy risk guidance (CBOE/OIC educational materials, and the same order of
magnitude used by every major "wheel strategy" risk-management writeup): a premium-selling
sleeve carries assignment risk (full notional exposure to the underlying, not just the premium
collected) and PIN/gap risk around earnings and macro events that a stock position of the same
dollar size doesn't carry in the same concentrated way, so it should be sized meaningfully
*smaller* than a comparable equity sleeve, not equal to one. 5% caps the maximum realistic
damage from a full-sleeve blowup (e.g. every open CSP getting assigned into a gap-down) to a
low single-digit percentage of total equity — survivable, not existential.

This number is a **starting point for the pilot phase, not permanent** — see §8 (review
cadence). It is deliberately conservative because this sleeve has zero live track record.

## 1. Instrument scope

**Cash-secured puts (CSP) and covered calls (the classic "wheel"), nothing else, for the
pilot.** No long calls/puts, no spreads, no naked calls.

Reasoning:
- Both legs are fully collateralized — CSP by cash, covered call by owned shares. No
  undefined/naked risk, no margin-call exposure distinct from what equity positions already
  carry.
- Matches Alpaca options-approval **level 1** (see `scripts/check_options_approval_status.py`)
  — the lowest approval tier, which is the realistic near-term state of this account (status
  unknown as of 2026-09-12, being checked now). Anything requiring level 2/3 approval is out
  of scope until there's a reason to request a higher tier.
- Matches what `algo/signals/signal_options.py`'s dead `SignalOptionsMixin` methods
  (`iv_rank_signal`, `put_call_ratio_signal`, `implied_move_signal`) were already built
  toward and what the screener's 0.15-0.30 delta band in
  `lambda/api/routes/options.py:_CANDIDATE_DELTA_LOW/_CANDIDATE_DELTA_HIGH` already
  implements — this spec formalizes numbers the code already leans toward rather than
  inventing new ones.

## 2. Underlying eligibility

An underlying is eligible for the sleeve only if **all** of:

- Already a member of `market_constituents` (the same universe the equity strategy scores —
  no new universe to maintain).
- **Optionable with real liquidity**: options-chain `open_interest >= 100` and
  `volume >= 10` on the specific contract being considered (not just "the underlying has
  options listed" — a listed-but-illiquid chain produces wide bid/ask spreads that eat the
  premium edge). Options-chain liquidity is checked in addition to, not instead of, the
  equity liquidity gates the loader/screener already apply upstream.
- **Not already an open equity position** in the same underlying (see §6, equity-overlap
  rule) — the sleeve and the equity strategy must never both have capital at risk in the same
  name at the same time.
- Composite score (existing 5-pillar equity score) is not in the bottom quintile of the
  scored universe. Rationale: selling a CSP is an implicit willingness to own the stock at
  the strike if assigned — don't accept assignment risk on names the existing scoring system
  is already flagging as low-quality/low-momentum. This reuses the existing score rather than
  building new fundamental logic for the options sleeve.
- No earnings announcement scheduled before the contract's expiration date (avoids
  event-driven IV-crush/gap risk that the 0.15-0.30 delta band alone doesn't protect against).

## 3. Entry criteria

**Cash-secured puts:**
- `|delta|` between 0.15 and 0.30 (matches the existing screener band — sell far enough OTM
  that assignment is the minority outcome, not the base case).
- Days-to-expiration (DTE) between 30 and 45 at entry (matches the loader's stated intent —
  `scripts/options_data_loader.py`'s risk-free-rate comment already targets this window; the
  loader's actual chain fetch currently takes "nearest 2 expirations" without an explicit DTE
  filter, which is a real gap between stated intent and current code — **tracked as a phase-4
  fix**, not something this spec papers over).
- IV rank >= 50 (using `iv_rank_signal`'s existing 0-100 definition, current IV vs 1-year
  high/low). Selling premium when implied vol is elevated relative to the underlying's own
  history is the entire edge of a premium-selling strategy; skip low-IV-rank names even if
  delta/DTE otherwise match, because there's insufficient premium to justify the assignment
  risk.
- Strike <= current support level or a round number reasonably below spot (avoid strikes
  sitting exactly at a known resistance/support pivot where gamma risk concentrates) — a soft
  preference applied at candidate-ranking time, not a hard gate.

**Covered calls** (only written against shares the sleeve already owns via CSP assignment,
never against equity-strategy shares — see §6):
- Same delta (0.15-0.30) and DTE (30-45) bands as CSPs, symmetric logic on the call side.
- Strike >= cost basis from assignment (never write a covered call that locks in a loss below
  the assigned price, unless explicitly rolling to manage an existing losing position — see
  §5).

## 4. Position sizing within the sleeve

- Per-underlying cap: no more than **20% of the sleeve's total capital** in any single
  underlying (5 positions fully diversifies the sleeve at the cap; mirrors the same
  concentration-limit philosophy as the equity strategy's `max_positions_per_sector` control,
  scaled to the sleeve's much smaller total size).
- Sector cap: no more than **40% of the sleeve's total capital** in any single GICS sector
  (looser than the per-underlying cap since a handful of correlated names in one sector is a
  real but smaller risk than concentration in one name).
- Collateral for every open CSP must be cash the sleeve actually holds — no assumption of
  margin, no "buying power" cushion borrowed from the equity sleeve. This is a strict
  cash-secured (not margin-secured) posture for the pilot.

## 5. Assignment, roll, and exit rules

- **Assignment is an expected outcome, not a failure.** A CSP assigned at the strike converts
  into 100 shares held inside the sleeve (tracked separately from equity-strategy holdings —
  see §6) at cost basis = strike - premium collected. Immediately becomes eligible for the
  covered-call leg per §3.
- **Roll a CSP** (buy to close, sell a new further-dated put at a lower strike) when: DTE <= 7
  and the position is still open (avoid gamma/pin risk in the final week) AND the roll can be
  done for a net credit. If no net-credit roll is available at DTE <= 7, let assignment
  happen rather than rolling for a debit (a debit roll is paying to defer a loss, not
  managing risk).
- **Close early for profit** at 50% of max profit (premium collected) — standard
  premium-selling practice (locks in the edge, frees collateral for the next entry, avoids
  holding for the last, most gamma-exposed portion of value decay for a shrinking marginal
  gain).
- **Covered call assignment** (shares called away) closes that underlying's position in the
  sleeve entirely — proceeds return to sleeve cash, eligible for a new CSP cycle on a
  (possibly different) eligible underlying.
- **Hard stop on the underlying**: if the underlying drops >15% from the CSP's strike while
  the put is open (a real adverse move, not normal premium decay), close the put immediately
  regardless of premium P&L rather than waiting for assignment or expiration — same
  "protect capital over optimizing for the last dollar of premium" logic as the equity
  strategy's stop-loss discipline.

## 6. Equity-overlap rule (hard, not advisory)

The sleeve and the equity strategy must **never** both hold exposure to the same underlying
at the same time:
- Before entering a new CSP, check the underlying has no open equity-strategy position.
- Before the equity strategy enters a new position, check the underlying has no open
  sleeve exposure (CSP or assigned shares).
- If both somehow end up flagged for the same underlying (a race, or a manual override), the
  sleeve's leg is the one that gets closed — the equity strategy's sizing/stop logic assumes
  it's the only source of exposure to a name, and retrofitting it to share exposure
  accounting with the sleeve is out of scope for the pilot.

This is the concrete form of "standalone sleeve, not interleaved with equity sizing" from the
phase-1 design decision — it needs to be enforced in code (phase 4/5), not just stated here.

## 7. Go/no-go gate (blocks phase 5, execution)

Before any real order submission code goes live, **all** of:
1. Dedicated options backtest (phase 3) shows positive net edge after realistic costs —
   commission, bid/ask slippage on entry AND exit/roll, and assignment/pin-risk modeling —
   over a period covering at least one full high-volatility regime (2020, 2022 or 2026-08
   drawdown-comparable window), not just a calm-market sample.
2. Risk/collateral infrastructure (phase 4) is live: a real `algo_options_positions` table,
   collateral accounting that can't double-count cash already committed to open CSPs, and the
   sleeve's own pretrade checks wired into the existing `halt_flag_manager` (same halt
   propagation the equity strategy already has — not a parallel, disconnected halt system).
3. Alpaca account confirmed options-approved at the required level (§1) —
   `scripts/check_options_approval_status.py` run with real credentials, not assumed.
4. Minimum paper-trading track record on this exact sleeve logic — **60 calendar days or 20
   completed CSP/covered-call cycles, whichever is longer** — mirroring
   `scripts/verify_live_trading_readiness.py`'s existing equity-strategy precedent of
   requiring a real paper-trading track record before real orders, not just a clean backtest.
5. This spec itself has been re-read and re-confirmed current (not silently stale) by
   whoever is about to flip the sleeve live.

## 8. Review cadence

The 5%-of-equity cap, the delta/DTE bands, and the per-underlying/sector caps in §4 are pilot
defaults, not permanent constants. Revisit them explicitly after the phase-3 backtest results
exist (a backtest showing the edge concentrates in a narrower delta band, or that 30-45 DTE
underperforms 45-60 DTE, should change §3/§4 before phase 5, not after) and again after the
first 90 days of live trading once the sleeve is live. Any change to the cap percentage itself
should be a deliberate, written decision the same way this doc is — not an ad hoc edit under
time pressure.

## Phase 3 status: backtest built and run (2026-09-12)

`algo/backtest/run_options_backtest.py` (commit `0586610bf`) implements a synthetic
Black-Scholes wheel backtest — **read its module docstring before trusting any number
below**: `options_chains`/`iv_history` only started accumulating today, so there is no real
historical vendor options-quote data to replay yet. This backtest prices every hypothetical
CSP/covered-call using trailing realized volatility (× a documented, conservative 1.15
volatility-risk-premium multiplier) as an IV proxy — evidence about the mechanical
construction (delta band/DTE/assignment), not the same evidence a real historical-quote
backtest would give.

Run against real local `price_daily` history, 35 liquid symbols, 2020-01 to 2024-06
(spans both the COVID crash and the 2022 bear market): **1,427 cycles, 85.7% win rate,
+1.14% avg return on collateral per cycle**, still positive when isolated to 2022 alone
(+0.60% avg/cycle, 315 cycles). Saved as `backtest_runs.run_id=2`.

**Verdict**: directionally positive signal, grounds to continue into phase 4
(risk/collateral infrastructure) — but NOT grounds to treat §7's go/no-go gate item 1 as
satisfied. Real historical options data (a paid vendor, or waiting years for the daily
loader to accumulate its own history) is still needed to actually confirm the edge before
phase 5 (real execution).

v1 scope gaps carried forward (not simulated): early-close-at-50%-profit, DTE<=7 rolls, the
>15%-underlying-drop stop rule (spec §5), and the composite-score eligibility filter (spec
§2 — `stock_scores` has no historical date dimension to backtest against without look-ahead
bias). None of these affect the core edge-sign question v1 answers; they're risk-management
refinements for a v2 once a real-data backtest justifies further investment.

## Open items carried into phase 3+

- Loader's "nearest 2 expirations" behavior vs. this spec's 30-45 DTE target (§3) — needs a
  real DTE filter added to `scripts/options_data_loader.py`, tracked as a phase-4 item since
  it's infrastructure, not strategy-rule, work.
- Alpaca options-approval level: unknown as of this writing, being checked via
  `scripts/check_options_approval_status.py` (requires real credentials this local session
  doesn't have — needs to be run somewhere `AlpacaSyncManager` can resolve them, e.g. via AWS
  Secrets Manager access, and the result recorded back into this doc and memory).
- `terraform/modules/loaders/main.tf`'s `options_data_loader` schedule is written but not
  applied (carried over from phase 1) — needs `terraform apply` before the sleeve can depend
  on same-day data freshness for real trading, independent of everything else in this spec.

## Phase 4 status: risk/collateral infrastructure built (2026-09-12)

Built exactly the go/no-go item 2 infrastructure described in §7 — no execution code, no
order submission, nothing wired into any live orchestrator phase (there is nothing yet for
it to gate):

- **`migrations/versions/1285_create_algo_options_positions.sql`**: new `algo_options_positions`
  table tracking the full lifecycle from §5 — `id`, `symbol`, `sector`, `option_type`,
  `strategy_leg` ('csp'/'covered_call'), `strike`, `expiration_date`, `contracts`,
  `entry_date`, `entry_premium`, `collateral_amount` (cash collateral for an open CSP; 0/NULL
  for a covered call, which is share-collateralized), `status` ('open'/'assigned'/'closed'/
  'rolled'/'expired', CHECK-constrained), `cost_basis` (set on CSP assignment),
  `assigned_shares`, a self-referential `rolled_from_id` for roll chains, `closed_date`,
  `exit_price`, `realized_pnl`. Indexed on `(symbol, status)` and `(status)` since collateral
  accounting filters `WHERE status = 'open'` constantly. Guarded with `IF NOT EXISTS`
  throughout (same phantom-migration discipline this session's CLAUDE.md documents for
  `options_chains`/`iv_history`), with a regression test
  (`tests/unit/test_migration_1285_options_positions_fresh_db_safe.py`) proving it applies
  cleanly to a genuinely fresh database.
- **`algo/risk/options_collateral.py`**: pure accounting — `compute_committed_collateral()`
  is the single source of truth (sums `collateral_amount` over `status = 'open'` rows only,
  so assigned/closed/rolled/expired positions can never be double-counted alongside their
  replacement rows), `available_sleeve_capital()` (5% of equity minus committed, floored at
  0), `underlying_exposure_pct()`/`sector_exposure_pct()` (open-CSP collateral + assigned
  cost-basis exposure, as a % of the sleeve's total 5% capital), and `has_equity_overlap()`.
- **`algo/risk/circuit_breaker_options.py`**: `check_options_pretrade()`, returning the same
  `{"halted", "halt_reasons", "checks"}` shape `CircuitBreaker.check_all()` already uses.
  Covers sleeve-cap, per-underlying-cap (20%), sector-cap (40%), no-equity-overlap, and
  cash-collateral-actually-available (no margin assumption). The one condition serious
  enough to trip a real trading halt — committed collateral negative, or already exceeding
  the sleeve cap on its own, both signs the accounting itself is broken rather than "this
  candidate doesn't fit" — routes through `algo.orchestration.halt_flag_manager.
  HaltFlagManager.set_halt_flag(triggered_by="circuit_breaker_options")`, the same halt
  propagation the equity strategy already uses, not a parallel mechanism. **Not called from
  anywhere live** — it is what phase 5's future order-submission code is expected to call
  before submitting any CSP/covered-call order.
- **DTE filter fix** (the phase-4 item flagged in phase 3's "Open items" above):
  `scripts/options_data_loader.py` previously fetched the nearest `MAX_EXPIRATIONS` (2)
  listed expirations with no DTE filter at all. Now computes DTE for every listed
  expiration first, keeps only those inside a 27–48-day band (a small pad around the spec's
  30–45-day target to absorb weekly-vs-monthly expiration-date jitter), and takes the
  nearest `MAX_EXPIRATIONS` of those — so a name whose two nearest listed expirations are
  both outside the target band now correctly yields zero captured expirations that day
  rather than silently capturing off-band contracts.

**Still open, unchanged from phase 3:**
- No execution/order-submission code exists (phase 5 not started).
- Alpaca options-approval level is still unknown — `scripts/check_options_approval_status.py`
  still needs to be run with real credentials somewhere `AlpacaSyncManager` can resolve them.
- `terraform/modules/loaders/main.tf`'s `options_data_loader` schedule is still written but
  not applied.

**Documented gap from this phase, closed same-session (2026-09-12):** the equity-overlap rule
(§6) was initially enforced only in the sleeve-entering-checks-equity direction
(`has_equity_overlap()`, called from `check_options_pretrade`'s `no_equity_overlap` check).
The other direction has since been wired in: `algo/orchestrator/phase8_entry_execution.py`'s
per-candidate pre-filter loop now calls `has_equity_overlap()` for every candidate symbol
before it reaches position sizing, skipping (fail-closed on error) any symbol the sleeve
already has open/assigned exposure to. `has_equity_overlap()` itself needed no change — it
was already symmetric (checks both `algo_positions` and `algo_options_positions`); only the
missing caller was the gap. Both directions of §6 are now enforced in code, ahead of phase 5
rather than during it.

## Phase 5 status: still blocked, not started (as of 2026-09-12)

Per §7's go/no-go gate, phase 5 (real order-submission code) remains explicitly not started.
Checked again this session — no change to either blocker:
- **Alpaca options-approval level still unknown.** `scripts/check_options_approval_status.py`
  re-run from this local session again fails to resolve credentials (no `APCA_API_KEY_ID`/
  `APCA_API_SECRET_KEY` env vars, no AWS Secrets Manager access here) — same constraint as
  when this was first flagged in phase 2. Must be run somewhere `AlpacaSyncManager` can reach
  real credentials before phase 5 can start.
- **Backtest is still proxy-IV evidence only** (§7 item 1) — no real historical options-quote
  data exists to replay yet; unblocking this needs either a paid vendor or years of the daily
  loader accumulating its own history.
- `terraform/modules/loaders/main.tf`'s `options_data_loader` and `xbrl_second_opinion`
  schedules are both still written but not applied — independent of the phase 5 gate itself,
  but real same-day options-chain freshness depends on the loader schedule actually running,
  not just being defined. Applying real AWS infrastructure changes is intentionally left as a
  decision for whoever has real AWS access to confirm, not something to run silently from
  here.
