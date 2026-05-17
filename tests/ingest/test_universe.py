# tests/ingest/test_universe.py
from ingest.universe import UNIVERSE, Contract, sectors

def test_contract_has_market_type():
    for c in UNIVERSE:
        assert c.market_type in ("physical", "financial"), f"{c.symbol} missing market_type"

def test_contract_has_report_type():
    for c in UNIVERSE:
        assert c.report_type in ("disagg", "tff"), f"{c.symbol} missing report_type"

def test_market_type_matches_report_type():
    for c in UNIVERSE:
        if c.market_type == "physical":
            assert c.report_type == "disagg"
        else:
            assert c.report_type == "tff"

def test_universe_size_at_least_50():
    assert len(UNIVERSE) >= 50, f"only {len(UNIVERSE)} contracts"

def test_financial_sectors_present():
    secs = {c.sector for c in UNIVERSE}
    assert "fx" in secs
    assert "indices" in secs
    assert "rates" in secs

def test_symbols_unique():
    syms = [c.symbol for c in UNIVERSE]
    assert len(syms) == len(set(syms))
