"""Regression test (2026-09-06, goal: "SEC/XBRL missing data to zero" sweep, ownership-data
investigation): three foreign private issuers' real, institution-held CUSIPs were falling
through _resolve_crosswalk_ticker's fallback chain to "no_resolved_13f_holdings" even though
real 13F data exists for them - live-verified via SEC's own 13F full-text search (PUK: 878
hits, BCH: 5,994 hits, PAC: 430 hits) and, for PUK, a real infoTable.xml filing (accession
0001085146-25-003989, CUSIP 74435K204, nameOfIssuer="PRUDENTIAL PLC").

OpenFIGI's raw ticker for each CUSIP isn't a real tracked symbol (PUKN/G4RA/G9N), so
resolution falls to EntityNameIndex.find(resolved_name) - which fails for all three: PUK's
case ties against Prudential Financial Inc (PRU) on the shared "PRUDENTIAL" token (a
cross-company name collision, same shape as BIO-RAD's dual-class collision already aliased in
this file); BCH's and PAC's cases share zero tokens at all between OpenFIGI's Spanish legal
name and our English-translated local entity_name (a translation mismatch, not a tie).
"""

from loaders.load_institutional_holdings_13f import InstitutionalHoldings13FLoader


class _NoneEntityNameIndex:
    """Stand-in for the real EntityNameIndex - always returns None, matching this fix's
    verified real-world finding that the name-index rescue genuinely fails for all three
    cases (tie or zero-overlap), so the verified alias is the only path that resolves them."""

    def find(self, resolved_name):
        return None


class TestInstitutionalHoldings13FFpiTranslatedNameAliases:
    def test_prudential_plc_adr_resolves_via_alias(self):
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="PUKN",
            resolved_name="PRUDENTIAL PLC-ADR",
            symbols={"PUK", "PRU"},
            local_names={"PUK": "PRUDENTIAL PLC", "PRU": "PRUDENTIAL FINANCIAL INC"},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker == "PUK"

    def test_banco_de_chile_adr_resolves_via_alias(self):
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="G4RA",
            resolved_name="BANCO DE CHILE-ADR",
            symbols={"BCH"},
            local_names={"BCH": "BANK OF CHILE"},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker == "BCH"

    def test_grupo_aeroportuario_pac_adr_resolves_via_alias(self):
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="G9N",
            resolved_name="GRUPO AEROPORTUARIO PAC-ADR",
            symbols={"PAC"},
            local_names={"PAC": "Pacific Airport Group"},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker == "PAC"

    def test_grupo_aeroportuario_cen_adr_resolves_via_alias(self):
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="G7A",
            resolved_name="GRUPO AEROPORTUARIO CEN-ADR",
            symbols={"OMAB"},
            local_names={"OMAB": "Central North Airport Group"},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker == "OMAB"

    def test_bbva_argentina_adr_resolves_via_raw_ticker_alias_alone(self):
        # Unlike BCH/PAC/OMAB above, BBAR's OpenFIGI resolved_name shares real tokens
        # (BBVA/ARGENTINA/SA) with the local entity_name, so no companion
        # _VERIFIED_BRAND_NAME_ALIASES entry is needed - the raw-ticker alias alone suffices.
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="BFP",
            resolved_name="BBVA ARGENTINA SA-ADR",
            symbols={"BBAR"},
            local_names={"BBAR": "Banco BBVA Argentina S.A."},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker == "BBAR"

    def test_saneamento_basico_adr_resolves_via_raw_ticker_alias_alone(self):
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="SAJA",
            resolved_name="CIA SANEAMENTO BASICO DE-ADR",
            symbols={"SBS"},
            local_names={"SBS": "COMPANHIA DE SANEAMENTO BASICO DO ESTADO DE SAO PAULO-SABESP"},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker == "SBS"

    def test_unrelated_raw_ticker_and_name_still_fails(self):
        # Guard against the alias dict being too permissive - a genuinely unresolvable
        # (raw_ticker, resolved_name) pair not in the verified alias set must still return
        # None, not silently match on a partial key.
        ticker = InstitutionalHoldings13FLoader._resolve_crosswalk_ticker(
            raw_ticker="ZZZZ",
            resolved_name="SOME UNRELATED COMPANY",
            symbols={"PUK", "BCH", "PAC"},
            local_names={"PUK": "PRUDENTIAL PLC", "BCH": "BANK OF CHILE", "PAC": "Pacific Airport Group"},
            name_index=_NoneEntityNameIndex(),
        )
        assert ticker is None
