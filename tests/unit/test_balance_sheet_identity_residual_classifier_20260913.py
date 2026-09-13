"""Unit tests for scripts/balance_sheet_identity_residual_classifier.py's SIGNATURES matching
logic - the pure, DB-independent part of the classifier. Guards against a signature silently
matching (or failing to match) the exact real-world shapes it was written for, since a wrong
match here would misreport how much of the confirmed-fresh backlog is actually explained.
"""

from scripts.balance_sheet_identity_residual_classifier import SIGNATURES

_BY_NAME = {sig.name: sig for sig in SIGNATURES}


class TestNciDoubleCountSignature:
    def test_matches_agro_shaped_row(self) -> None:
        # AGRO FY2024 real values: liab+eq alone == assets, nci adds on top.
        row = {
            "assets": 3_114_888_000.0,
            "liab": 1_706_787_000.0,
            "eq": 1_408_101_000.0,
            "nci": 38_951_000.0,
            "te": 0.0,
        }
        row["residual"] = row["assets"] - (row["liab"] + row["eq"] + row["nci"] + row["te"])
        assert _BY_NAME["nci_double_count"].matches(row)

    def test_does_not_match_when_nci_is_zero(self) -> None:
        row = {"assets": 100.0, "liab": 40.0, "eq": 40.0, "nci": 0.0, "te": 0.0, "residual": 20.0}
        assert not _BY_NAME["nci_double_count"].matches(row)

    def test_does_not_match_unrelated_residual(self) -> None:
        # residual doesn't align with -nci at all - a different, unclassified cause.
        row = {"assets": 1000.0, "liab": 400.0, "eq": 400.0, "nci": 10.0, "te": 0.0, "residual": 200.0}
        assert not _BY_NAME["nci_double_count"].matches(row)


class TestTempEquityDoubleCountSignature:
    def test_matches_when_residual_equals_negative_te(self) -> None:
        # liab + eq alone already sum to assets (500); te=100 on top overshoots by exactly te.
        row = {"assets": 500.0, "liab": 250.0, "eq": 250.0, "nci": 0.0, "te": 100.0}
        row["residual"] = row["assets"] - (row["liab"] + row["eq"] + row["nci"] + row["te"])
        assert row["residual"] == -100.0
        assert _BY_NAME["temp_equity_double_count"].matches(row)


class TestTempEquityMissingEntirelySignature:
    def test_matches_hdrn_shaped_row(self) -> None:
        # HDRN FY2025 real values: liab+eq tiny relative to assets, nci/te both zero -
        # the SPAC trust-account gap this signature exists to flag as "known, not a quick fix".
        row = {
            "assets": 211_878_016.0,
            "liab": 3_641_177.0,
            "eq": -3_300_471.0,
            "nci": 0.0,
            "te": 0.0,
        }
        row["residual"] = row["assets"] - (row["liab"] + row["eq"] + row["nci"] + row["te"])
        assert _BY_NAME["temp_equity_missing_entirely"].matches(row)

    def test_does_not_match_ordinary_company_with_normal_liabilities(self) -> None:
        row = {"assets": 1000.0, "liab": 600.0, "eq": 400.0, "nci": 0.0, "te": 0.0, "residual": 0.0}
        assert not _BY_NAME["temp_equity_missing_entirely"].matches(row)

    def test_does_not_match_when_nci_present(self) -> None:
        # Same tiny-liab+eq shape, but nci is nonzero - that's nci_double_count's territory,
        # not this signature's.
        row = {"assets": 200_000_000.0, "liab": 3_000_000.0, "eq": -2_000_000.0, "nci": 500_000.0, "te": 0.0}
        row["residual"] = row["assets"] - (row["liab"] + row["eq"] + row["nci"] + row["te"])
        assert not _BY_NAME["temp_equity_missing_entirely"].matches(row)


class TestSignatureRegistryShape:
    def test_signature_names_are_unique(self) -> None:
        names = [sig.name for sig in SIGNATURES]
        assert len(names) == len(set(names))

    def test_every_signature_has_a_nonempty_note(self) -> None:
        for sig in SIGNATURES:
            assert sig.note.strip()
