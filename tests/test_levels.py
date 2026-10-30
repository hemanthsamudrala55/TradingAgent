from master_agent import levels


def test_range_support_and_resistance_found_with_evidence(range_bound):
    lv = levels.find_levels(range_bound)
    assert lv["available"]
    s, r = lv["immediate_support"], lv["immediate_resistance"]
    assert 98 <= s["level"] <= 101, s
    assert 119 <= r["level"] <= 122, r
    assert s["count"] >= 3 and r["count"] >= 3
    # each level is backed by real swing points inside the data
    for t in s["touches"] + r["touches"]:
        row = range_bound.loc[t["date"]]
        assert t["price"] in (round(row.high, 2), round(row.low, 2))


def test_no_resistance_means_price_discovery():
    import numpy as np
    from tests.conftest import frame
    lv = levels.find_levels(frame(list(np.linspace(50, 150, 300))))
    assert lv["immediate_resistance"] is None and lv["price_discovery"]


def test_needs_enough_data():
    from tests.conftest import frame
    assert not levels.find_levels(frame([10] * 20))["available"]
