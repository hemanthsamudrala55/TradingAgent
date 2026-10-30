import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def frame(closes, start="2024-01-01", spread=0.01, vol=100_000):
    idx = pd.bdate_range(start, periods=len(closes))
    c = np.asarray(closes, float)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + spread / 2)
    l = np.minimum(o, c) * (1 - spread / 2)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": np.full(len(c), vol, float)}, index=idx)


@pytest.fixture
def range_bound():
    """Uptrend to 100, then four swings between ~100 and ~120."""
    up = list(np.linspace(50, 100, 220))
    leg = list(np.linspace(100, 120, 15)) + list(np.linspace(120, 100, 15))
    return frame(up + leg * 4 + list(np.linspace(100, 108, 6)))
