"""Regression test: _fetch_all_prices() used to drop every price_daily row with volume == 0,
not just invalid (close<=0) rows.

Found live 2026-08-20 while investigating trend_template_data.weinstein_stage's elevated NULL
rate (health check reported 16.4%, threshold 5%): several real symbols with 700-4300+ days of
price_daily history still had NULL sma_200 (and for the worst cases, NULL sma_50 too) in
technical_data_daily despite ample raw history. Root cause: "sleepy" dual-class share tickers
(MOG.B, TAP.A, HVT.A, AKO.A, WSO.B, AGM.A) routinely report 0 consolidated-tape volume on days
that still have a valid last-sale close - live-confirmed 65%-86% of their rows in a 400-day
window have volume=0. The old `if volume is not None and volume == 0: continue` guard (originally
meant to exclude halted-stock rows) deleted these rows' close prices entirely, shrinking the
effective close-price series below what sma_200/sma_50 need even though 250+ raw rows existed -
and for symbols that cleared 50 bars but not 200, the surviving series was quietly gappy
(non-contiguous trading days), silently distorting SMA/RSI/MACD/ROC instead of nulling them.

Fix: only reject rows with an invalid close (None or <= 0). volume=0 is preserved as a real,
low (not hidden) value, which volume_ma_50 legitimately reflects.
"""

from datetime import date, timedelta

from loaders.load_technical_indicators import VectorizedTechnicalLoader


def _rows(symbol: str, num_days: int, end_date: date, zero_volume_indices: set[int] = frozenset()) -> list:
    out = []
    for i in range(num_days):
        d = end_date - timedelta(days=num_days - 1 - i)
        close = 10.0 + i * 0.01
        volume = 0 if i in zero_volume_indices else 1_000_000
        out.append((symbol, d, close, close * 1.01, close * 0.99, close, volume))
    return out


class TestZeroVolumeRowsNotDropped:
    def test_zero_volume_rows_kept_with_valid_close(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        end_date = date.today()
        zero_indices = {5, 10, 15, 20}
        rows = _rows("MOG.B", 60, end_date, zero_volume_indices=zero_indices)
        monkeypatch.setattr(loader, "_fetch_price_batch", lambda symbols, start, end: rows)

        result = loader._fetch_all_prices(["MOG.B"], end_date - timedelta(days=59), end_date)

        assert len(result) == 60, "zero-volume rows with a valid close must not be dropped"
        zero_vol_dates = {rows[i][1] for i in zero_indices}
        kept_dates_with_zero_vol = {r["date"] for r in result if r["date"] in zero_vol_dates}
        assert kept_dates_with_zero_vol == zero_vol_dates
        for r in result:
            if r["date"] in zero_vol_dates:
                assert r["volume"] == 0
                assert r["close"] is not None

    def test_invalid_close_still_dropped(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        end_date = date.today()
        rows = _rows("ZZZZ", 10, end_date)
        # Corrupt one row's close to 0 (invalid) and one to None
        bad_rows = list(rows)
        bad_rows[3] = ("ZZZZ", rows[3][1], rows[3][2], rows[3][3], rows[3][4], 0.0, rows[3][6])
        bad_rows[7] = ("ZZZZ", rows[7][1], rows[7][2], rows[7][3], rows[7][4], None, rows[7][6])
        monkeypatch.setattr(loader, "_fetch_price_batch", lambda symbols, start, end: bad_rows)

        result = loader._fetch_all_prices(["ZZZZ"], end_date - timedelta(days=9), end_date)

        assert len(result) == 8
        assert rows[3][1] not in {r["date"] for r in result}
        assert rows[7][1] not in {r["date"] for r in result}
