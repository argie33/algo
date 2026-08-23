#!/usr/bin/env python3
"""Regression test for a 2026-08-23 fix in algo/signals/signal_patterns.py::vcp_detection().

vcp_detection()'s docstring always claimed a real Minervini VCP requires each successive
contraction to show LOWER volume alongside smaller depth, but the implementation never fetched
or checked volume at all - is_vcp was gated purely on depth contraction. Fixed by fetching
volume, computing an average volume per leg, and requiring the last leg's average volume to be
<= 70% of the first leg's (VCP_CONTRACTION_FACTOR, reusing the same idiom already established
for depth) before is_vcp can be True. Also added a null-OHLCV guard mirroring base_detection()'s
existing 2026-08-09 fix for the same bug class (a NULL volume on a real gap day previously would
have raised a bare TypeError).

Uses a hand-constructed price series with 4 clearly separated single-bar peaks (11-bar-radius
local maxima, spaced 16 bars apart) and controlled trough depths/leg volumes, so the depth-
contraction and volume-dryup conditions can be independently controlled and verified.
"""

from itertools import pairwise
from unittest.mock import MagicMock, patch

from algo.signals.signal_patterns import SignalPatternsMixin


def _build_vcp_series(volumes_per_leg):
    """4 peaks at indices 6/22/38/54, ramping down to a trough then back up between each pair.

    Depths (computed by vcp_detection from peak highs and trough lows) contract each leg:
    leg1 ~20%, leg2 ~14% (<=0.7*20), leg3 ~9% (<=0.7*14) - satisfies VCP_MIN_DEPTHS=3 and
    VCP_MIN_CONTRACTIONS=2 regardless of volume. volumes_per_leg (3 values) controls the volume
    dry-up gate independently.
    """
    peaks = [(6, 12.0), (22, 11.8), (38, 11.6), (54, 11.4)]
    troughs = [(14, 9.6), (30, 10.148), (46, 10.556)]  # depths ~20.0%, ~14.0%, ~9.0%
    length = 60

    def _interp(control_points):
        arr = [0.0] * length
        for (idx_a, val_a), (idx_b, val_b) in pairwise(control_points):
            span = idx_b - idx_a
            for idx in range(idx_a, idx_b + 1):
                frac = (idx - idx_a) / span if span else 0.0
                arr[idx] = val_a + (val_b - val_a) * frac
        return arr

    # highs: strictly ramp UP into the first peak and DOWN out of the last peak (not flat at the
    # peak's own height, which previously let a neighboring index tie for the peak's local max),
    # dipping to each trough index between consecutive peaks so peak-finding sees real bumps.
    high_points = [(0, peaks[0][1] - 1.0)]
    for (p_idx, p_high), (t_idx, t_low) in zip(peaks, troughs, strict=False):
        high_points.append((p_idx, p_high))
        high_points.append((t_idx, t_low))
    high_points.append(peaks[-1])
    high_points.append((length - 1, peaks[-1][1] - 1.0))
    highs = _interp(high_points)

    # lows: its OWN ramp (not derived from highs * constant) so the exact trough value lands
    # precisely at the intended index without being undercut by a still-elevated nearby point on
    # a shared ramp - that mismatch previously shifted computed leg depths by ~0.2pp, flipping
    # the >=2-contraction boundary check.
    low_points = [(0, (peaks[0][1] - 1.0) * 0.98)]
    for (p_idx, p_high), (t_idx, t_low) in zip(peaks, troughs, strict=False):
        low_points.append((p_idx, p_high * 0.99))
        low_points.append((t_idx, t_low))
    low_points.append((peaks[-1][0], peaks[-1][1] * 0.99))
    low_points.append((length - 1, (peaks[-1][1] - 1.0) * 0.98))
    lows = _interp(low_points)

    volumes = [0.0] * length

    # Volume: constant baseline outside the peak windows, overridden per-leg to control the
    # leg-average used by vols_per_leg.
    leg_bounds = [(6, 22), (22, 38), (38, 54)]
    for (p1, p2), vol in zip(leg_bounds, volumes_per_leg, strict=True):
        for idx in range(p1, p2 + 1):
            volumes[idx] = vol

    return highs, lows, volumes


def _classify_with_fake_cursor(mixin, operation_result_setup):
    fake_cursor = MagicMock()

    def fake_with_cursor(operation):
        return operation(fake_cursor)

    with patch.object(mixin, "_with_cursor", side_effect=fake_with_cursor):
        return operation_result_setup()


class TestVcpVolumeGate:
    def test_depth_contracts_but_volume_flat_is_not_vcp(self):
        highs, lows, volumes = _build_vcp_series([500_000.0, 500_000.0, 500_000.0])
        mixin = SignalPatternsMixin()
        result = _classify_with_fake_cursor(
            mixin,
            lambda: mixin.vcp_detection(
                "FLATVOL", "2026-08-21", _prefetched={"highs": highs, "lows": lows, "volumes": volumes}
            ),
        )
        assert result["contractions"] >= 2
        assert result["volume_dryup_confirmed"] is False
        assert result["is_vcp"] is False

    def test_depth_and_volume_both_contract_is_vcp(self):
        highs, lows, volumes = _build_vcp_series([1_000_000.0, 700_000.0, 500_000.0])
        mixin = SignalPatternsMixin()
        result = _classify_with_fake_cursor(
            mixin,
            lambda: mixin.vcp_detection(
                "REALVCP", "2026-08-21", _prefetched={"highs": highs, "lows": lows, "volumes": volumes}
            ),
        )
        assert result["contractions"] >= 2
        assert result["volume_dryup_confirmed"] is True
        assert result["is_vcp"] is True

    def test_null_volume_row_returns_data_unavailable_not_crash(self):
        mixin = SignalPatternsMixin()
        fake_cursor = MagicMock()
        # 30 rows (VCP_MIN_BARS), one with a NULL volume on a real gap day.
        rows = [("2026-08-01", 10.0, 9.5, 9.8, 100000.0) for _ in range(29)]
        rows.append(("2026-08-30", 10.0, 9.5, 9.8, None))
        fake_cursor.fetchall.return_value = rows

        def fake_with_cursor(operation):
            return operation(fake_cursor)

        with patch.object(mixin, "_with_cursor", side_effect=fake_with_cursor):
            result = mixin.vcp_detection("GAPDAY", "2026-08-21")

        assert result["data_unavailable"] is True
        assert result["reason"] == "null_ohlcv_in_price_history"
        assert result["is_vcp"] is None
