import pandas as pd
import pytest
from ingest.tff_cot import _parse_tff_df, compute_net_columns

SAMPLE_ROW = {
    "As_of_Date_In_Form_YYMMDD": 260117,
    "Market_and_Exchange_Names": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
    "CFTC_Contract_Market_Code": "099741",
    "Dealer_Positions_Long_All": 400000,
    "Dealer_Positions_Short_All": 450000,
    "Asset_Mgr_Positions_Long_All": 300000,
    "Asset_Mgr_Positions_Short_All": 200000,
    "Lev_Money_Positions_Long_All": 100000,
    "Lev_Money_Positions_Short_All": 280000,
    "Other_Rept_Positions_Long_All": 10000,
    "Other_Rept_Positions_Short_All": 8000,
    "NonRept_Positions_Long_All": 15000,
    "NonRept_Positions_Short_All": 20000,
    "Open_Interest_All": 825000,
}

def test_parse_renames_columns():
    df = pd.DataFrame([SAMPLE_ROW])
    result = _parse_tff_df(df)
    assert "dealer_long" in result.columns
    assert "am_long" in result.columns
    assert "lf_long" in result.columns
    assert "open_interest" in result.columns

def test_net_commercials_computed():
    df = pd.DataFrame([SAMPLE_ROW])
    parsed = _parse_tff_df(df)
    result = compute_net_columns(parsed)
    # dealer net = 400000 - 450000 = -50000
    assert result["net_commercials"].iloc[0] == -50000

def test_report_date_parsed():
    df = pd.DataFrame([SAMPLE_ROW])
    result = _parse_tff_df(df)
    assert pd.api.types.is_datetime64_any_dtype(result["report_date"])

def test_missing_columns_raises():
    df = pd.DataFrame([{"As_of_Date_In_Form_YYMMDD": 260117}])
    with pytest.raises(KeyError):
        _parse_tff_df(df)
