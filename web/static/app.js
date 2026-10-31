/* Trading Agent dashboard. Plain JS; charts via lightweight-charts 4.1.3. */
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const inr = v => v == null ? "—" : "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const num = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("en-IN", { maximumFractionDigits: d });
const pct = v => v == null ? "—" : `<span class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : ""}${num(v)}%</span>`;
const signed = v => v == null ? "—" : `<span class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : ""}${inr(v)}</span>`;
const pill = (t, k = "") => `<span class="pill ${k}">${esc(t)}</span>`;
const verdictKind = v => ({ ENTER: "up", HOLD: "up", WAIT: "warn", "AVOID CHASING": "warn", AVOID: "down", EXIT: "down" }[v] || "");

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}
async function busy(btn, fn) {
  const t = btn.textContent; btn.disabled = true; btn.textContent = "Working…";
  try { await fn(); } finally { btn.disabled = false; btn.textContent = t; }
}
const card = (title, body, extra = "") => `<div class="card" ${extra}><h3>${title}</h3>${body}</div>`;
const table = (heads, rows) => `<div class="scroll"><table class="tbl"><thead><tr>${heads.map(h => `<th class="${h.endsWith(" ") ? "n" : ""}">${h.trim()}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;

/* ---------- tabs ---------- */
const loaded = {};
function show(tab) {
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("on", s.id === "tab-" + tab));
  history.replaceState(null, "", "#" + tab);
  if (!loaded[tab]) { loaded[tab] = true; ({ live: loadLive, assumptions: loadAssumptions, instructions: loadInstructions }[tab] || (() => {}))(); }
}
$("#tabs").addEventListener("click", e => e.target.dataset.tab && show(e.target.dataset.tab));

/* ---------- status ---------- */
let STATUS = {};
async function loadStatus() {
  STATUS = await api("/api/status");
  const k = STATUS.kite;
  $("#conn").innerHTML = k.connected
    ? `${pill("Zerodha connected", "up")} <span class="muted">${esc(k.user || "")}</span>`
    : `${pill("Zerodha not connected", "warn")} <a href="/kite/login" target="_blank" rel="noopener">Connect Zerodha</a>`;
  $("#conn").innerHTML += ` <span class="muted small">Data: ${STATUS.default_source === "kite" ? "Kite" : "Yahoo"}</span>`;
}

/* ---------- analyze ---------- */
$("#ask").addEventListener("submit", e => {
  e.preventDefault();
  busy($("#ask button"), async () => {
    $("#out").innerHTML = "";
    try {
      const r = await api("/api/analyze", { symbol: $("#sym").value, query: $("#q").value, source: $("#src").value });
      renderAnalysis(r);
    } catch (err) { $("#out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
  });
});

$("#upl").addEventListener("submit", async e => {
  e.preventDefault();
  const fd = new FormData(); fd.append("symbol", $("#upl-sym").value); fd.append("file", $("#upl-file").files[0]);
  try {
    const r = await fetch("/api/upload-chart", { method: "POST", body: fd }).then(r => r.json());
    if (r.error) throw new Error(r.error);
    $("#upl-msg").textContent = `Loaded ${r.candles} candles for ${r.symbol} (${r.from} → ${r.to}). Choose "My uploaded chart" and Analyze.`;
    $("#sym").value = r.symbol; $("#src").value = "upload";
  } catch (err) { $("#upl-msg").textContent = err.message; }
});

function renderAnalysis(r) {
  const S = new Set(r.route.sections), t = r.technical, out = [];
  out.push(`<div class="mode">${pill("Mode " + r.route.mode + " · " + r.route.mode_name, "up")} <b>${esc(r.symbol)}</b>
    ${t ? `<span class="muted">${esc(r.source)} · ${t.candles_used} daily candles · as of ${t.as_of}</span>` : ""}</div>`);
  if (r.route.assumed) out.push(`<div class="note">${esc(r.route.assumed)}</div>`);
  if (r.technical_error) out.push(`<div class="err">${esc(r.technical_error)}</div>`);
  if (r.fundamentals_error && [..."ACVDQ"].includes(r.route.mode)) out.push(`<div class="err">${esc(r.fundamentals_error)}</div>`);

  const f = r.fundamentals;
  if (f && S.has("dashboard")) out.push(dashboardCard(f));
  if (f && S.has("metrics")) out.push(metricsCard(f, r.route.fund_metrics));
  if (f && S.has("valuation")) out.push(valuationCard(f));
  if (t && S.has("quick")) out.push(quickCard(r));
  if (t && (S.has("positional") || S.has("technical"))) out.push(planCard(r.plan));
  if (t && S.has("chart")) out.push(card("Chart · daily", `<div class="legend">
      <span><i style="background:var(--ema21)"></i>EMA 21</span><span><i style="background:var(--ema63)"></i>EMA 63</span>
      <span><i style="background:var(--ema200)"></i>EMA 200</span><span><i style="background:var(--up)"></i>Support</span>
      <span><i style="background:var(--down)"></i>Resistance</span><span>● swing points that form the nearest levels</span></div>
      <div id="chart"></div><div id="rsi-chart"></div>`));
  if (t && (S.has("levels") || S.has("technical"))) out.push(levelsCard(t.levels));
  const techCards = [];
  if (t && (S.has("ema") || S.has("technical"))) techCards.push(emaCard(t));
  if (t && (S.has("rsi") || S.has("technical"))) techCards.push(rsiCard(t.rsi));
  if (t && (S.has("volume") || S.has("technical"))) techCards.push(volumeCard(t.volume));
  if (t && (S.has("delivery") || S.has("technical"))) techCards.push(deliveryCard(t.delivery));
  if (t && (S.has("gaps") || S.has("technical"))) techCards.push(gapCard(t.gaps));
  if (t && (S.has("trend") || S.has("technical"))) techCards.push(trendCard(t.trend));
  if (techCards.length) out.push(`<div class="grid2">${techCards.join("")}</div>`);
  if (t && (S.has("candles") || S.has("technical"))) out.push(candleCard(t.candles));
  if (S.has("compare")) out.push(`<div id="cmp-out" class="card">Loading comparison…</div>`);
  if (S.has("portfolio")) out.push(`<div class="note">Portfolio questions are answered on the <a href="#portfolio" onclick="show('portfolio')">Portfolio vs benchmark</a> tab.</div>`);
  out.push(`<p class="muted small">Verified data = values from the named source and date. Interpretation and verdicts are the engine's rules (see Assumptions). Nothing here is a guaranteed outcome or a forced BUY/SELL.</p>`);
  $("#out").innerHTML = out.join("");
  if (t && S.has("chart") && r.chart) drawChart(r.chart, t.levels, r.plan);
  if (S.has("compare")) runCompare(r.route.symbols);
}

/* -- fundamentals -- */
function dashboardCard(f) {
  const cats = {}; f.rows.forEach(x => (cats[x.category] ||= []).push(x));
  const cols = Object.entries(cats).map(([c, rows]) => `<div><h4>${c}</h4><table class="tbl">${rows.map(x =>
    `<tr><td>${esc(x.metric)}${x.note ? `<div class="muted small">${esc(x.note)}</div>` : ""}</td><td class="n">${x.value === "Unavailable" ? `<span class="muted">Unavailable</span>` : esc(x.value)}</td></tr>`).join("")}</table></div>`);
  return card(`Screener dashboard · ${esc(f.name || "")}`, `<div class="grid3">${cols.join("")}</div>
    <p class="muted small">Source: <a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.source)}</a>, observed ${f.observed}.
    ${f.unavailable.length ? `Unavailable (not shown publicly or not on the page): ${esc(f.unavailable.join(", "))}.` : ""}</p>`);
}
function metricsCard(f, wanted) {
  const want = new Set(wanted || []);
  const rows = f.rows.filter(x => want.has(x.metric));
  return card("Requested metrics", table(["Metric", "Value ", "Note"], rows.map(x => `<tr><td>${esc(x.metric)}</td><td class="n">${esc(x.value)}</td><td class="muted small">${esc(x.note)}</td></tr>`))
    + `<p class="muted small">Source: ${esc(f.source)}, ${f.observed}</p>`);
}
function valuationCard(f) {
  const g = f.graham;
  return card("Valuation", `<div class="kpis">
      <div class="kpi"><div class="l">Current price</div><div class="v">${inr(f.cmp)}</div></div>
      <div class="kpi"><div class="l">Graham Number</div><div class="v">${g.value ? inr(g.value) : "—"}</div><div class="muted small">${esc(g.formula || g.reason || "")}</div></div>
      <div class="kpi"><div class="l">Margin of safety (Graham)</div><div class="v">${pct(f.graham_margin_of_safety_pct)}</div></div></div>
    <h4>DCF (your assumptions)</h4>
    <form class="row" id="dcf"><label>FCF base (₹ Cr) <input name="fcf_base" type="number" step="any" required></label>
      <label>Shares (Cr) <input name="shares" type="number" step="any" required></label>
      <label>Growth % <input name="growth_pct" type="number" value="12" step="any"></label>
      <label>Years <input name="years" type="number" value="5"></label>
      <label>Discount % <input name="discount_pct" type="number" value="12" step="any"></label>
      <label>Terminal % <input name="terminal_pct" type="number" value="4" step="any"></label>
      <label>Net debt (₹ Cr) <input name="net_debt" type="number" value="0" step="any"></label>
      <button class="primary">Calculate</button></form><div id="dcf-out"></div>
    <p class="muted small">Intrinsic value is an estimate, not a verified market fact. A DCF is only as good as the FCF base and assumptions entered.</p>`);
}
document.addEventListener("submit", async e => {
  if (e.target.id !== "dcf") return;
  e.preventDefault();
  const b = Object.fromEntries(new FormData(e.target));
  try {
    const r = await api("/api/dcf", b);
    const keys = Object.keys(r.sensitivity[0]).filter(k => k !== "discount_pct");
    $("#dcf-out").innerHTML = `<p><b>Intrinsic value per share: ${inr(r.result.value)}</b> <span class="muted">(terminal value = ${r.result.terminal_share_pct}% of EV)</span></p>` +
      table(["Discount rate", ...keys.map(k => k + " ")], r.sensitivity.map(x => `<tr><td>${x.discount_pct}%</td>${keys.map(k => `<td class="n">${inr(x[k])}</td>`).join("")}</tr>`));
  } catch (err) { $("#dcf-out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
});

/* -- positional plan -- */
function planBlock(p, title) {
  if (!p) return "";
  const rows = [];
  if (p.entry_zone) rows.push(["Entry zone", `${inr(p.entry_zone[0])} – ${inr(p.entry_zone[1])}`]);
  if (p.trigger) rows.push(["Trigger", esc(p.trigger)]);
  if (p.trigger_level) rows.push(["Cleared resistance", inr(p.trigger_level)]);
  rows.push(["Entry (for R:R)", inr(p.entry)], ["Stop-loss", `${inr(p.stop)} <span class="muted">(${num(p.risk_pct)}% · ${inr(p.risk_per_share)}/share)</span>`],
    ["Target 1", `${inr(p.t1.price)} <span class="muted small">${esc(p.t1.basis)}</span>`],
    ["Target 2", `${inr(p.t2.price)} <span class="muted small">${esc(p.t2.basis)}</span>`],
    ["Risk : reward", `T1 ${num(p.rr_t1)}R · T2 ${num(p.rr_t2)}R`]);
  if (p.volume_x_avg != null) rows.push(["Breakout volume", `${num(p.volume_x_avg)}× 20-day avg ${p.volume_confirmed ? pill("confirmed", "up") : pill("not confirmed", "warn")}`]);
  return `<h4>${title}</h4><table class="tbl">${rows.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("")}</table>`;
}
function planCard(p) {
  if (!p) return "";
  if (!p.confirmed) return card("Positional trade plan", `<div class="verdict">${pill(p.verdict, "down")}</div><p>${esc(p.reason)}</p>`);
  return card("Positional trade plan", `<div class="row"><span class="verdict">${pill(p.verdict, verdictKind(p.verdict))}</span>
      <span>Trend: <b>${esc(p.trend)}</b></span><span>Momentum: <b>${esc(p.momentum)}</b> (RSI ${num(p.rsi, 1)})</span>
      <span>Volume ${num(p.volume_x_avg)}× avg</span><span>Gap today ${pct(p.gap_today_pct)}</span>
      <span class="muted">Timeframe assumed: ${esc(p.assumed_timeframe)}</span></div>
    <ul class="tight">${p.reasons.map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <div class="grid2"><div>${planBlock(p.pullback_plan, "Pullback entry")}</div><div>${planBlock(p.breakout_plan, p.breakout_plan && p.breakout_plan.type === "breakout" ? "Breakout entry (today)" : "Alternative: breakout entry")}</div></div>
    <div class="grid2"><div><h4>Trade is invalid if</h4><ul class="tight">${p.invalidation.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>
    <div><h4>Risks</h4><ul class="tight">${p.risks.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div></div>`);
}
function quickCard(r) {
  const p = r.plan, t = r.technical;
  return card("Quick update", `<ul class="tight"><li>Close ${inr(t.close)} on ${t.as_of}; ${esc(t.ema.structure || "")}</li>
    <li>RSI ${num(t.rsi.value, 1)} – ${esc(t.rsi.zone || "")}</li>
    <li>Nearest support ${t.levels.immediate_support ? inr(t.levels.immediate_support.level) : "none"} · nearest resistance ${t.levels.immediate_resistance ? inr(t.levels.immediate_resistance.level) : "none (price discovery)"}</li>
    <li>Setup: ${pill(p.verdict, verdictKind(p.verdict))} ${esc((p.reasons || [p.reason])[0] || "")}</li></ul>`);
}

/* -- levels -- */
function zoneRow(label, z) {
  if (!z) return `<tr><td>${label}</td><td colspan="4" class="muted">None in the data</td></tr>`;
  return `<tr><td>${label}</td><td class="n"><b>${inr(z.level)}</b></td><td class="n">${inr(z.low)} – ${inr(z.high)}</td>
    <td class="n">${z.count}${z.weekly_confirmed ? " " + pill("weekly", "up") : ""}${z.role_reversal ? " " + pill("role reversal") : ""}</td>
    <td class="small">${z.touches.map(t => `${t.date} ${t.kind === "swing high" ? "H" : "L"} ${num(t.price)}`).join("<br>")}</td></tr>`;
}
function levelsCard(L) {
  if (!L.available) return card("Support & resistance", `<p>${esc(L.reason)}</p>`);
  const zl = (zs, k) => zs.map((z, i) => `<tr><td>${k}${i + 1}</td><td class="n">${inr(z.level)}</td><td class="n">${inr(z.low)} – ${inr(z.high)}</td><td class="n">${z.count}</td><td>${z.last_touch}</td></tr>`).join("");
  return card("Support & resistance", `${table(["Level", "Price ", "Zone ", "Touches ", "Evidence (swing points)"], [
      zoneRow("Major resistance", L.major_resistance), zoneRow("Immediate resistance", L.immediate_resistance),
      `<tr><td colspan="5" class="muted">Close ${inr(L.close)} · ATR ${inr(L.atr)} · zone tolerance ±${inr(L.zone_tolerance)}</td></tr>`,
      zoneRow("Immediate support", L.immediate_support), zoneRow("Strong support", L.strong_support)])}
    <div class="grid2"><div><h4>All resistance zones</h4>${table(["", "Level ", "Zone ", "Touches ", "Last touch"], [zl(L.resistances, "R")])}</div>
      <div><h4>All support zones</h4>${table(["", "Level ", "Zone ", "Touches ", "Last touch"], [zl(L.supports, "S")])}</div></div>
    <div class="row small"><span>52-week high ${inr(L.high_52w)} / low ${inr(L.low_52w)}</span>
      <span>Breakout level ${inr(L.breakout_level)}</span><span>Breakdown level ${inr(L.breakdown_level)}</span>
      <span>Last swing high ${L.last_swing_high ? inr(L.last_swing_high.price) + " (" + L.last_swing_high.date + ")" : "—"}</span>
      <span>Last swing low ${L.last_swing_low ? inr(L.last_swing_low.price) + " (" + L.last_swing_low.date + ")" : "—"}</span>
      ${L.consolidation ? `<span>Consolidation ${inr(L.consolidation.low)}–${inr(L.consolidation.high)} for ${L.consolidation.bars} sessions</span>` : ""}
      ${L.price_discovery ? pill("No resistance overhead – price discovery", "warn") : ""}</div>
    <p class="muted small">Every level is a cluster of real swing highs/lows (5 bars each side) from the last year of daily candles; the dates above let you find each touch on your chart.</p>`);
}

/* -- technical cards -- */
function emaCard(t) {
  const e = t.ema, w = t.weekly;
  if (!e.available) return card("EMA 21 / 63 / 200", `<p>${esc(e.reason)}</p>`);
  const row = (k, n) => `<tr><td>${n}</td><td class="n">${inr(e.values[k])}</td><td>${e.price_vs[k]}</td><td class="n">${pct(e.distance_pct[k])}</td><td>${e.slopes[k]}</td>
      <td>${w.available && w[k] != null ? inr(w[k]) + " · " + w["price_vs_" + k] : "—"}</td></tr>`;
  return card("EMA 21 / 63 / 200", `<p><b>${esc(e.structure)}</b> ${e.overextended ? pill("overextended", "warn") : ""}</p>
    ${table(["", "Daily ", "Price is", "Distance ", "Slope", "Weekly"], [row("ema21", "EMA 21"), row("ema63", "EMA 63"), row("ema200", "EMA 200")])}
    <p class="small">EMA 21 is ${e.ema21_vs_ema63} EMA 63 · EMA 63 is ${e.ema63_vs_ema200} EMA 200</p>
    ${e.events_recent.length ? `<ul class="tight small">${e.events_recent.map(x => `<li>${x.date}: ${esc(x.event)}</li>`).join("")}</ul>` : ""}`);
}
function rsiCard(r) {
  if (!r.available) return card("RSI 14", `<p>${esc(r.reason)}</p>`);
  return card("RSI 14", `<p><span class="verdict">${num(r.value, 1)}</span> ${esc(r.zone)}</p>
    <ul class="tight"><li>Direction: ${r.direction} (${r.change_5d >= 0 ? "+" : ""}${num(r.change_5d, 1)} over 5 sessions)</li>
    ${r.midline_cross ? `<li>${esc(r.midline_cross)}</li>` : ""}
    ${r.divergences.map(d => `<li><b>${d.type}</b> ${d.from} → ${d.to}: ${esc(d.detail)}</li>`).join("")}
    ${r.failure_swing ? `<li>${esc(r.failure_swing)}</li>` : ""}</ul>`);
}
function volumeCard(v) {
  if (!v.available) return card("Volume", `<p>${esc(v.reason)}</p>`);
  return card("Volume", `<p>Today ${num(v.today, 0)} vs 20-day avg ${num(v.avg20, 0)} = <b>${num(v.ratio_to_avg)}×</b></p>
    <p>${esc(v.pattern)} <span class="muted small">(up/down volume ratio ${num(v.updown_volume_ratio)})</span></p>
    ${v.high_volume_days.length ? `<ul class="tight small">${v.high_volume_days.map(d => `<li>${d.date}: ${d.x_avg}× avg, ${d.move} day</li>`).join("")}</ul>` : ""}`);
}
function deliveryCard(d) {
  if (!d.available) return card("Delivery %", `<p class="muted">${esc(d.reason)}</p>`);
  return card("Delivery %", table(["Current ", "5-day ", "10-day ", "20-day ", "Up days ", "Down days "],
    [`<tr>${[d.current, d.avg5, d.avg10, d.avg20, d.on_up_days_20, d.on_down_days_20].map(x => `<td class="n">${num(x)}%</td>`).join("")}</tr>`]) +
    `<p class="muted small">${esc(d.source)}, as of ${d.as_of}. ${esc(d.note)}</p>`);
}
function gapCard(g) {
  return card("Gaps", `<p>Previous close ${inr(g.prev_close)} · today open ${inr(g.today_open)} (${pct(g.today_gap_pct)})</p>` +
    (g.recent_gaps.length ? table(["Date", "Type", "Gap ", "Prev close ", "Open ", "Volume ", "Filled"], g.recent_gaps.map(x =>
      `<tr><td>${x.date}</td><td>${x.direction}</td><td class="n">${pct(x.gap_pct)}</td><td class="n">${inr(x.prev_close)}</td><td class="n">${inr(x.open)}</td><td class="n">${num(x.volume_x_avg)}×</td><td>${x.filled ? "yes" : "no"}</td></tr>`))
      : `<p class="muted">No gaps of 2%+ in the last 20 sessions.</p>`));
}
function trendCard(t) {
  return card("Trend structure", `<p><b>${esc(t.structure)}</b></p><p class="small">Recent swing highs ${t.swing_highs.map(num).join(" → ") || "—"}<br>Recent swing lows ${t.swing_lows.map(num).join(" → ") || "—"}</p>
    ${t.notes.length ? `<ul class="tight">${t.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : ""}`);
}
function candleCard(c) {
  if (!c.length) return card("Candlestick patterns · last 60 sessions", `<p class="muted">No patterns found.</p>`);
  const last = c.slice(-25).reverse();
  return card("Candlestick patterns · last 60 sessions", table(["Date", "Pattern", "Bias", "Close ", "Context"], last.map(x =>
    `<tr><td>${x.date}</td><td>${esc(x.pattern)}</td><td>${pill(x.bias, x.bias === "bullish" ? "up" : x.bias === "bearish" ? "down" : "")}</td><td class="n">${inr(x.close)}</td><td>${x.context}</td></tr>`)) +
    (c.length > 25 ? `<p class="muted small">Showing the latest 25 of ${c.length}.</p>` : ""));
}

/* -- chart -- */
let charts = [];
function baseChart(el, h) {
  return LightweightCharts.createChart(el, {
    height: h, autoSize: true,
    layout: { background: { color: css("--panel") }, textColor: css("--muted"), fontSize: 11 },
    grid: { vertLines: { color: css("--line") }, horzLines: { color: css("--line") } },
    rightPriceScale: { borderColor: css("--line") }, timeScale: { borderColor: css("--line") },
    crosshair: { mode: 0 },
  });
}
function drawChart(c, L, plan) {
  charts.forEach(x => x.remove()); charts = [];
  const ch = baseChart($("#chart"), 440);
  const up = css("--up"), dn = css("--down");
  const cs = ch.addCandlestickSeries({ upColor: up, downColor: dn, wickUpColor: up, wickDownColor: dn, borderVisible: false });
  cs.setData(c.candles);
  const vol = ch.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
  ch.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
  vol.setData(c.volume.map(v => ({ time: v.time, value: v.value, color: (v.up ? up : dn) + "55" })));
  [["ema21", "--ema21"], ["ema63", "--ema63"], ["ema200", "--ema200"]].forEach(([k, col]) =>
    ch.addLineSeries({ color: css(col), lineWidth: 1.5, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false }).setData(c[k]));
  const line = (price, color, title, style = 0, width = 1) => price && cs.createPriceLine({ price, color, lineWidth: width, lineStyle: style, axisLabelVisible: true, title });
  const markers = [];
  if (L && L.available) {
    L.supports.forEach((z, i) => line(z.level, up, `S${i + 1} (${z.count})`, i ? 2 : 0, i ? 1 : 2));
    L.resistances.forEach((z, i) => line(z.level, dn, `R${i + 1} (${z.count})`, i ? 2 : 0, i ? 1 : 2));
    const firstTime = c.candles.length ? c.candles[0].time : "";
    [[L.immediate_support, up, "belowBar"], [L.immediate_resistance, dn, "aboveBar"]].forEach(([z, col]) => z && z.touches.forEach(t => {
      if (t.date >= firstTime) markers.push({ time: t.date, position: t.kind === "swing high" ? "aboveBar" : "belowBar", color: col, shape: "circle", text: num(t.price) });
    }));
  }
  const p = plan && plan.plan;
  if (p) {
    line(p.entry, css("--accent"), "Entry", 1); line(p.stop, dn, "Stop", 1);
    line(p.t1 && p.t1.price, up, "T1", 1); line(p.t2 && p.t2.price, up, "T2", 1);
  }
  markers.sort((a, b) => a.time < b.time ? -1 : 1);
  cs.setMarkers(markers);
  ch.timeScale().setVisibleLogicalRange({ from: Math.max(0, c.candles.length - 180), to: c.candles.length + 5 });

  const rc = baseChart($("#rsi-chart"), 130);
  const rs = rc.addLineSeries({ color: css("--accent"), lineWidth: 1.5, priceLineVisible: false });
  rs.setData(c.rsi);
  [70, 50, 30].forEach(v => rs.createPriceLine({ price: v, color: css("--muted"), lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "" }));
  ch.timeScale().subscribeVisibleLogicalRangeChange(r => r && rc.timeScale().setVisibleLogicalRange(r));
  charts = [ch, rc];
}

/* -- compare (mode E) -- */
async function runCompare(syms) {
  try {
    const r = await api("/api/compare", { symbols: syms, source: $("#src").value });
    const metrics = ["Market Capitalization", "Current Market Price", "Stock P/E", "ROCE", "ROE", "Debt-to-Equity", "OPM", "Promoter Holding", "QoQ Sales Growth", "Graham Number"];
    const val = (row, m) => row.fundamentals ? (row.fundamentals.rows.find(x => x.metric === m) || {}).value : "Unavailable";
    $("#cmp-out").innerHTML = `<h3>Comparison</h3>` + table(["Metric", ...r.rows.map(x => x.symbol + " ")], [
      ...metrics.map(m => `<tr><td>${m}</td>${r.rows.map(x => `<td class="n">${esc(val(x, m))}</td>`).join("")}</tr>`),
      `<tr><td>EMA structure</td>${r.rows.map(x => `<td class="n small">${esc(x.ema_structure || x.technical_error || "—")}</td>`).join("")}</tr>`,
      `<tr><td>Positional setup</td>${r.rows.map(x => `<td class="n">${x.plan ? pill(x.plan.verdict, verdictKind(x.plan.verdict)) : "—"}</td>`).join("")}</tr>`]) +
      `<p class="muted small">No single ratio decides the stronger company; read each category together.</p>`;
  } catch (err) { $("#cmp-out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
}

/* ---------- setups ---------- */
$("#scan-go").addEventListener("click", e => busy(e.target, async () => {
  try {
    const syms = $("#scan-syms").value.split(",").map(s => s.trim()).filter(Boolean);
    const r = await api("/api/scan", { symbols: syms.length ? syms : null, source: $("#src").value });
    $("#scan-out").innerHTML = card(`Positional setups · ${esc(r.source)}`, table(["Symbol", "Verdict", "Close ", "Trend", "RSI ", "Entry ", "Stop ", "T1 ", "R:R ", "Why"], r.rows.map(x => x.error
      ? `<tr><td>${x.symbol}</td><td colspan="9" class="neg small">${esc(x.error)}</td></tr>`
      : `<tr><td><a href="#analyze" onclick="openSym('${x.symbol}')">${x.symbol}</a></td><td>${pill(x.verdict, verdictKind(x.verdict))}</td><td class="n">${inr(x.close)}</td><td>${esc(x.trend || "")}</td><td class="n">${num(x.rsi, 1)}</td>
          <td class="n">${x.plan ? inr(x.plan.entry) : "—"}</td><td class="n">${x.plan ? inr(x.plan.stop) : "—"}</td><td class="n">${x.plan ? inr(x.plan.t1.price) : "—"}</td><td class="n">${x.plan ? num(x.plan.rr_t1) : "—"}</td>
          <td class="small">${esc((x.reasons || [])[0] || "")}</td></tr>`)));
  } catch (err) { $("#scan-out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
}));
function openSym(s) { show("analyze"); $("#sym").value = s; $("#q").value = "positional trading"; $("#ask").requestSubmit(); }

/* ---------- simulation / paper ---------- */
function simView(r, title) {
  const k = (l, v) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  return `<div class="kpis">${k("Final equity", inr(r.final_equity))}${k("Return", pct(r.return_pct))}${r.benchmark_return_pct != null ? k(esc(r.benchmark_name), pct(r.benchmark_return_pct)) : ""}
      ${k("Max drawdown", pct(r.max_drawdown_pct))}${k("Closed trades", r.trades)}${k("Win rate", r.win_rate_pct == null ? "—" : num(r.win_rate_pct, 1) + "%")}${k("Avg R", num(r.avg_r))}${k("Charges", inr(r.charges))}</div>
    ${r.note ? `<div class="note">${esc(r.note)}</div>` : ""}
    ${card(title + " · equity", `<div id="eq-${title}" style="height:300px"></div><p class="muted small">${esc(r.source)} · ${r.symbols.length} symbols${r.skipped.length ? " · skipped: " + esc(r.skipped.map(s => s.symbol).join(", ")) : ""}</p>`)}
    ${card("Open positions", r.open_positions.length ? table(["Symbol", "Since", "Setup", "Qty ", "Entry ", "Last ", "Stop ", "T1 ", "T2 ", "Unrealised "], r.open_positions.map(p =>
      `<tr><td>${p.symbol}</td><td>${p.entry_date}</td><td>${p.setup}</td><td class="n">${p.qty}</td><td class="n">${inr(p.entry)}</td><td class="n">${inr(p.last)}</td><td class="n">${inr(p.stop)}</td><td class="n">${inr(p.t1)}${p.t1_done ? " ✓" : ""}</td><td class="n">${inr(p.t2)}</td><td class="n">${signed(p.unrealised)}</td></tr>`)) : `<p class="muted">None</p>`)}
    ${card("Closed trades", r.closed_trades.length ? table(["Symbol", "Setup", "Entry date", "Entry ", "Qty ", "Exit date", "Exit ", "Reason", "Net P&L ", "R "], r.closed_trades.slice().reverse().map(t =>
      `<tr><td>${t.symbol}</td><td>${t.setup}</td><td>${t.entry_date}</td><td class="n">${inr(t.entry)}</td><td class="n">${t.qty}</td><td>${t.exit_date}</td><td class="n">${inr(t.exit_price)}</td><td class="small">${esc(t.exit_reason)}</td><td class="n">${signed(t.net_pl)}</td><td class="n">${num(t.r_multiple)}</td></tr>`)) : `<p class="muted">None</p>`)}`;
}
function drawEquity(id, r) {
  const el = document.getElementById(id); if (!el) return;
  const ch = baseChart(el, 300);
  ch.addLineSeries({ color: css("--accent"), lineWidth: 2, title: "Strategy" }).setData(r.equity_curve.map(e => ({ time: e.date, value: e.equity })));
  if (r.benchmark_curve) ch.addLineSeries({ color: css("--muted"), lineWidth: 1, lineStyle: 2, title: "Nifty 50" }).setData(r.benchmark_curve.map(e => ({ time: e.date, value: e.equity })));
  ch.timeScale().fitContent();
}
function simRunner(prefix, path, title) {
  $(`#${prefix}-go`).addEventListener("click", e => busy(e.target, async () => {
    const out = $(`#${prefix}-out`);
    try {
      const syms = $(`#${prefix}-syms`).value.split(",").map(s => s.trim()).filter(Boolean);
      const body = { symbols: syms.length ? syms : null, start: $(`#${prefix}-start`).value, capital: $(`#${prefix}-cap`).value, source: $("#src").value };
      if (prefix === "sim") body.end = $("#sim-end").value;
      if (!body.start) throw new Error("Choose a start date");
      const r = await api(path, body);
      out.innerHTML = simView(r, title); drawEquity("eq-" + title, r);
    } catch (err) { out.innerHTML = `<div class="err">${esc(err.message)}</div>`; }
  }));
}
simRunner("sim", "/api/simulate", "Simulation");
simRunner("pap", "/api/paper", "Paper");

/* ---------- live ---------- */
async function loadLive() {
  const out = $("#live-out");
  out.innerHTML = `<p class="muted">Loading…</p>`;
  try {
    const r = await api("/api/live");
    if (!r.connected) {
      out.innerHTML = card("Live · Zerodha", `<p>Not connected${r.reason ? `: <span class="muted">${esc(r.reason)}</span>` : ""}.</p>
        <p><a href="/kite/login" target="_blank" rel="noopener"><button class="primary">Connect Zerodha</button></a></p>
        <p class="muted small">The live view is read-only: it shows holdings, positions and a HOLD / EXIT check against each stop. It never places orders.</p>`);
      return;
    }
    const tot = r.holdings.reduce((a, h) => a + h.pl, 0);
    out.innerHTML = card(`Holdings · ${esc(r.user || "")} <button style="float:right" onclick="loaded.live=false;loadLive()">Refresh</button>`,
      `<p>Total unrealised P&amp;L ${signed(tot)}</p>` + table(["Symbol", "Qty ", "Avg ", "LTP ", "P&L ", "Stop (GTT) ", "Check", "Nearest support ", "Nearest resistance ", "Note"], r.holdings.map(h => {
        const L = h.levels && h.levels.pullback_plan ? h.levels.pullback_plan.support_zone : null;
        const R = h.levels && h.levels.pullback_plan ? h.levels.pullback_plan.t1 : null;
        return `<tr><td><a href="#analyze" onclick="openSym('${h.symbol}')">${h.symbol}</a></td><td class="n">${h.qty}</td><td class="n">${inr(h.avg)}</td><td class="n">${inr(h.ltp)}</td><td class="n">${signed(h.pl)} ${pct(h.pl_pct)}</td>
          <td class="n">${h.gtt_stop ? inr(h.gtt_stop) : `<span class="neg">no GTT</span>`}</td><td>${h.check ? pill(h.check.verdict, verdictKind(h.check.verdict)) : "—"}</td>
          <td class="n">${L ? inr(L.level) : "—"}</td><td class="n">${R ? inr(R.price) : "—"}</td><td class="small">${esc(h.error || (h.check && h.check.reason) || "")}</td></tr>`;
      })) + `<p class="muted small">${esc(r.note)} When a holding has no GTT, the check uses the engine's support-based stop.</p>`) +
      card("Positions (today)", r.positions.length ? table(["Symbol", "Product", "Qty ", "Avg ", "LTP ", "P&L "], r.positions.map(p =>
        `<tr><td>${p.tradingsymbol}</td><td>${p.product}</td><td class="n">${p.quantity}</td><td class="n">${inr(p.average_price)}</td><td class="n">${inr(p.last_price)}</td><td class="n">${signed(p.pnl)}</td></tr>`)) : `<p class="muted">No open positions.</p>`);
  } catch (err) { out.innerHTML = `<div class="err">${esc(err.message)}</div>`; }
}

/* ---------- portfolio ---------- */
function addLot(l = {}) {
  const tr = document.createElement("tr");
  tr.innerHTML = `<td><input name="symbol" value="${esc(l.symbol || "")}" placeholder="TCS"></td><td><input name="date" type="date" value="${esc(l.date || "")}"></td>
    <td><input name="qty" type="number" step="any" value="${esc(l.qty || "")}"></td><td><input name="price" type="number" step="any" value="${esc(l.price || "")}"></td>
    <td><button type="button" onclick="this.closest('tr').remove()">✕</button></td>`;
  $("#lots tbody").appendChild(tr);
}
$("#lot-add").addEventListener("click", () => addLot());
$("#lot-kite").addEventListener("click", async () => {
  try { const r = await api("/api/holdings-as-lots"); $("#lots tbody").innerHTML = ""; r.lots.forEach(addLot);
    $("#pf-out").innerHTML = `<div class="note">Loaded ${r.lots.length} holdings. Zerodha does not report purchase dates – enter the date for each row.</div>`;
  } catch (err) { $("#pf-out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
});
function pfView(r) {
  const k = (l, v) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div></div>`;
  return `<div class="kpis">${k("Invested", inr(r.total_investment))}${k("Current value", inr(r.total_value))}${k("Profit / loss", signed(r.total_pl))}${k("Return", pct(r.portfolio_return_pct))}${k("Valuation date", r.valuation_date)}</div>
    ${card("Same money, same dates – vs benchmarks", table(["Investment", "Initial ", "Current ", "Profit / loss ", "Return ", "Source"], r.comparison.map(c =>
      `<tr><td><b>${esc(c.investment)}</b></td><td class="n">${inr(c.initial)}</td><td class="n">${inr(c.current)}</td><td class="n">${signed(c.pl)}</td><td class="n">${pct(c.return_pct)}</td><td class="small muted">${esc(c.source)}</td></tr>`)) +
      `<ul class="tight">${r.interpretation.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` +
      (r.benchmark_unavailable.length ? `<div class="note">Unavailable: ${r.benchmark_unavailable.map(b => `${esc(b.benchmark)} – ${esc(b.reason)}`).join("; ")}. Drop a CSV at state/benchmarks/&lt;id&gt;.csv to use your own export.</div>` : "") +
      (r.date_adjustments.length ? `<p class="muted small">${r.date_adjustments.map(esc).join("<br>")}</p>` : ""))}
    ${card("Each stock", table(["Stock", "Invested ", "Value ", "Dividends ", "P&L ", "Return ", "Weight ", "Contribution ", "Volatility ", "Max DD ", ...Object.keys(r.stocks[0] || {}).filter(x => x.startsWith("vs_")).map(x => "vs " + x.slice(3, -11) + " ")], r.stocks.map(s =>
      `<tr><td><b>${s.symbol}</b>${s.symbol === r.best ? " " + pill("best", "up") : s.symbol === r.worst && r.stocks.length > 1 ? " " + pill("worst", "down") : ""}</td><td class="n">${inr(s.investment)}</td><td class="n">${inr(s.current_value)}</td><td class="n">${inr(s.dividends)}</td><td class="n">${signed(s.pl)}</td><td class="n">${pct(s.return_pct)}</td><td class="n">${num(s.weight_pct)}%</td><td class="n">${num(s.contribution_pct_points)} pts</td><td class="n">${num(s.volatility_ann_pct)}%</td><td class="n">${pct(s.max_drawdown_pct)}</td>
       ${Object.keys(s).filter(x => x.startsWith("vs_")).map(x => `<td class="n">${num(s[x])} pts</td>`).join("")}</tr>`)) +
      `<h4>Benchmark risk over the same period</h4>` + table(["Benchmark", "Volatility ", "Max drawdown "], Object.entries(r.benchmark_risk).map(([n, v]) => `<tr><td>${esc(n)}</td><td class="n">${num(v.volatility_ann_pct)}%</td><td class="n">${pct(v.max_drawdown_pct)}</td></tr>`)) +
      `<h4>Lots</h4>` + table(["Stock", "Buy date", "Qty ", "Buy price ", "Split factor ", "CMP ", "Value ", "P&L ", "Return ", "Days ", "CAGR "], r.lots.map(l =>
        `<tr><td>${l.symbol}</td><td>${l.buy_date}</td><td class="n">${num(l.qty)}</td><td class="n">${inr(l.buy_price)}</td><td class="n">${l.split_factor}</td><td class="n">${inr(l.cmp)}</td><td class="n">${inr(l.current_value)}</td><td class="n">${signed(l.pl)}</td><td class="n">${pct(l.return_pct)}</td><td class="n">${l.holding_days}</td><td class="n">${l.cagr_pct == null ? "—" : pct(l.cagr_pct)}</td></tr>`)) +
      `<p class="muted small">Prices: ${esc(r.price_source)}. ${esc(r.dividends_note)}</p>`)}`;
}
$("#pf-go").addEventListener("click", e => busy(e.target, async () => {
  const lots = [...document.querySelectorAll("#lots tbody tr")].map(tr => Object.fromEntries([...tr.querySelectorAll("input")].map(i => [i.name, i.value])));
  try { $("#pf-out").innerHTML = pfView(await api("/api/portfolio", { lots, valuation_date: $("#pf-vdate").value })); }
  catch (err) { $("#pf-out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
}));
$("#wi-go").addEventListener("click", e => busy(e.target, async () => {
  try { $("#pf-out").innerHTML = pfView(await api("/api/portfolio", { what_if: { symbol: $("#wi-sym").value, amount: $("#wi-amt").value, months: $("#wi-m").value }, valuation_date: $("#pf-vdate").value })); }
  catch (err) { $("#pf-out").innerHTML = `<div class="err">${esc(err.message)}</div>`; }
}));

/* ---------- static pages ---------- */
async function loadAssumptions() { $("#assump").textContent = (await api("/api/assumptions")).text; }
function md(src) {
  // small Markdown renderer for the instruction document (headings, bold, lists, tables, paragraphs)
  const lines = src.split("\n"); let html = "", list = null, para = [], tbl = [];
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\*(.+?)\*/g, "<i>$1</i>");
  const flush = () => { if (para.length) { html += `<p>${inline(para.join(" "))}</p>`; para = []; } if (list) { html += `</${list}>`; list = null; }
    if (tbl.length) { html += `<table>${tbl.filter(r => !/^\|?\s*:?-{3,}/.test(r)).map((r, i) => `<tr>${r.replace(/^\||\|$/g, "").split("|").map(c => `<${i ? "td" : "th"}>${inline(c.trim())}</${i ? "td" : "th"}>`).join("")}</tr>`).join("")}</table>`; tbl = []; } };
  for (const l of lines) {
    if (/^\s*\|/.test(l)) { if (para.length || list) { const t = tbl; tbl = []; flush(); tbl = t; } tbl.push(l.trim()); continue; }
    const h = l.match(/^(#{1,4})\s+(.*)/), li = l.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
    if (h) { flush(); html += `<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`; }
    else if (li) { if (para.length) { const p = para; para = []; html += `<p>${inline(p.join(" "))}</p>`; } const t = /^\s*\d+\./.test(l) ? "ol" : "ul"; if (list !== t) { if (list) html += `</${list}>`; html += `<${t}>`; list = t; } html += `<li>${inline(li[1])}</li>`; }
    else if (!l.trim()) { flush(); }
    else if (list) { html += ""; flush(); para.push(l.trim()); }
    else para.push(l.trim());
  }
  flush(); return html;
}
async function loadInstructions() { $("#instr").innerHTML = md((await api("/api/instructions")).text); }

/* ---------- init ---------- */
(function init() {
  const today = new Date(), iso = d => d.toISOString().slice(0, 10);
  const ago = m => { const d = new Date(today); d.setMonth(d.getMonth() - m); return iso(d); };
  $("#sim-start").value = ago(12); $("#sim-end").value = iso(today); $("#pap-start").value = ago(1);
  addLot();
  loadStatus().catch(() => {});
  window.addEventListener("focus", () => { if (!STATUS.kite?.connected) loadStatus().catch(() => {}); });  // back from the Zerodha login tab
  show((location.hash || "#analyze").slice(1));
})();
