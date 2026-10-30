import pandas as pd

from master_agent import indicators as ind

# Wilder's worked example as published by StockCharts (70.53, 66.32, 66.55, 69.41, ...).
# StockCharts rounds intermediate averages to 2 dp, so unrounded maths lands within 0.1.
WILDER = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
          46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21]


def test_rsi_matches_wilder_reference():
    r = ind.rsi(pd.Series(WILDER), 14)
    assert r.iloc[:14].isna().all()
    ref = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93]
    for got, want in zip(r.iloc[14:], ref):
        assert abs(got - want) < 0.1


def test_ema_matches_standard_definition():
    s = pd.Series(range(1, 31), dtype=float)
    e = ind.ema(s, 21)
    alpha = 2 / 22
    ref = s.iloc[0]
    for x in s.iloc[1:]:
        ref = alpha * x + (1 - alpha) * ref
    assert abs(e.iloc[-1] - ref) < 1e-9


def test_pivots_tie_counts_once():
    from tests.conftest import frame
    df = frame([1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1, 2, 3])
    df.loc[df.index[6], "high"] = df["high"].iloc[5]   # equal highs on two bars
    ph, _ = ind.pivots(df, 3)
    assert ph.sum() == 1
