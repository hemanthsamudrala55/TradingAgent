import pandas as pd

from master_agent import data


def test_iso_dates_are_not_read_day_first():
    csv = b"Date,Open,High,Low,Close,Volume\n2024-01-02,1,2,0.5,1.5,100\n2024-01-03,1,2,0.5,1.6,100\n2024-02-01,1,2,0.5,1.7,100\n"
    df = data.read_csv(csv)
    assert list(df.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03"), pd.Timestamp("2024-02-01")]


def test_nse_style_day_first_dates_and_commas():
    csv = (b'Date,Open Price,High Price,Low Price,Close Price,Total Traded Quantity,% Dly Qt to Traded Qty\n'
           b'02-Jan-2024,"1,000",1010,990,1005,"12,345",45.5\n03-01-2024,1005,1020,1000,1015,100,50\n')
    df = data.read_csv(csv)
    assert list(df.index) == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert df["open"].iloc[0] == 1000 and df["volume"].iloc[0] == 12345 and df["deliv_pct"].iloc[0] == 45.5


def test_kite_rows_with_timezone():
    rows = pd.DataFrame([{"date": pd.Timestamp("2024-01-02 00:00:00+05:30"), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}])
    df = data.normalise(rows)
    assert df.index[0] == pd.Timestamp("2024-01-02") and df.index.tz is None
