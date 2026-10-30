from master_agent import fundamentals as f

HTML = """<html><h1>Test Ltd</h1><ul id="top-ratios">
<li><span class="name">Market Cap</span><span class="nowrap value">&#8377; <span class="number">12,345</span> Cr.</span></li>
<li><span class="name">Current Price</span><span class="nowrap value">&#8377; <span class="number">500</span></span></li>
<li><span class="name">High / Low</span><span class="nowrap value">&#8377; <span class="number">600</span> / <span class="number">400</span></span></li>
<li><span class="name">Stock P/E</span><span class="nowrap value"><span class="number">25.0</span></span></li>
<li><span class="name">Book Value</span><span class="nowrap value">&#8377; <span class="number">100</span></span></li>
<li><span class="name">ROCE</span><span class="nowrap value"><span class="number">20.5</span> %</span></li>
<li><span class="name">Face Value</span><span class="nowrap value">&#8377; <span class="number">10.0</span></span></li>
</ul>
<section id="quarters"><table><thead><tr><th></th><th>Mar 2026</th><th>Jun 2026</th></tr></thead>
<tbody><tr><td>Sales +</td><td>1,000</td><td>1,100</td></tr><tr><td>OPM %</td><td>18%</td><td>19%</td></tr></tbody></table></section>
<section id="profit-loss"><table><thead><tr><th></th><th>Mar 2025</th><th>TTM</th></tr></thead>
<tbody><tr><td>EPS in Rs</td><td>18</td><td>20</td></tr></tbody></table></section>
<section id="quarterly-shp"><table><thead><tr><th></th><th>Mar 2026</th><th>Jun 2026</th></tr></thead>
<tbody><tr><td>Promoters +</td><td>55.00%</td><td>54.50%</td></tr><tr><td>FIIs +</td><td>10.00%</td><td>11.25%</td></tr></tbody></table></section>
</html>"""


def test_dashboard_order_values_and_graham():
    d = f.dashboard(f.parse_screener(HTML))
    rows = {r["metric"]: r["value"] for r in d["rows"]}
    assert [r["metric"] for r in d["rows"]][:3] == ["Market Capitalization", "Current Market Price", "52-Week High / Low"]
    assert rows["Market Capitalization"] == "₹ 12,345 Cr."
    assert rows["ROCE"] == "20.5 %"
    assert rows["QoQ Sales Growth"] == "10.00 %"
    assert rows["Change in Promoter Holding"] == "-0.50 pts (QoQ)"
    assert rows["Change in FII Holding"] == "+1.25 pts (QoQ)"
    assert d["graham"]["value"] == 212.13          # sqrt(22.5 * 20 * 100)
    assert rows["ROIC"] == f.UNAVAILABLE and "ROIC" in d["unavailable"]


def test_graham_undefined_for_losses():
    assert f.graham_number(-5, 100)["value"] is None


def test_dcf_and_sensitivity():
    base = dict(fcf_base=100, shares=10, growth_pct=10, years=5, discount_pct=12, terminal_pct=4)
    v = f.dcf(**base)["value"]
    assert v > 0
    grid = f.dcf_sensitivity(base)
    assert len(grid) == 5 and grid[0]["tg 4%"] > v > grid[-1]["tg 4%"]
