/* Simple Trader: Stocks, Robot and Activity screens. Plain JS; charts via lightweight-charts 4.1.3. */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const inr = v => v == null ? "Unavailable" : "₹" + Number(v).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const whole = v => "₹" + Math.round(v).toLocaleString("en-IN");
const shares = v => v >= 1e7 ? (v / 1e7).toFixed(1) + " Cr" : v >= 1e5 ? (v / 1e5).toFixed(1) + " L" : Math.round(v).toLocaleString("en-IN");
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const j = await r.json();
  if (!r.ok || j.error) throw new Error(j.error || r.statusText);
  return j;
}

/* ---------- tabs ---------- */
function show(tab) {
  document.querySelectorAll("#tabs button").forEach(b => {
    const on = b.dataset.tab === tab;
    b.classList.toggle("on", on);
    if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("on", s.id === "tab-" + tab));
  history.replaceState(null, "", "#" + tab);
}
$("#tabs").addEventListener("click", e => e.target.dataset.tab && show(e.target.dataset.tab));

/* ---------- chart ---------- */
const FRAMES = {
  Hour: [42, "Each candle is 1 hour."], Day: [60, "Each candle is 1 day."], Month: [48, "Each candle is 1 month."],
  Quarter: [32, "Each candle is 3 months."], "Half-year": [24, "Each candle is 6 months."], Year: [16, "Each candle is 1 year."],
};
const UP = css("--up"), DOWN = css("--down");
let view = { symbol: "TCS", frame: "Day", rows: [], labels: {}, lines: [] };
let request = 0;

const chart = LightweightCharts.createChart($("#chart"), {
  autoSize: true,
  layout: { background: { color: "#FFFFFF" }, textColor: css("--muted"), fontSize: 12 },
  grid: { vertLines: { visible: false }, horzLines: { color: "#EEF1F4" } },
  rightPriceScale: { borderColor: css("--line"), scaleMargins: { top: 0.05, bottom: 0.28 } },
  timeScale: { borderColor: css("--line"), tickMarkFormatter: t => view.labels[t] || "" },
  localization: { timeFormatter: t => view.labels[t] || "" },
});
const candles = chart.addCandlestickSeries({ upColor: UP, downColor: DOWN, wickUpColor: UP, wickDownColor: DOWN, borderVisible: false, priceLineVisible: false });
const volume = chart.addHistogramSeries({ priceScaleId: "volume", priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false });
chart.priceScale("volume").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });

function readout(c) {
  if (!c) { $("#readout").innerHTML = ""; return; }
  $("#readout").innerHTML = `<b>${esc(c.label)}</b><span>Opened <b>${inr(c.open)}</b></span><span>Highest <b>${inr(c.high)}</b></span><span>Lowest <b>${inr(c.low)}</b></span><span>Closed <b>${inr(c.close)}</b></span><span>Volume <b>${shares(c.volume)}</b></span>`;
}
chart.subscribeCrosshairMove(p => {
  const c = p.time ? view.rows.find(r => r.time === p.time) : null;
  readout(c || view.rows[view.rows.length - 1]);
});

function renderFrames() {
  $("#frames").innerHTML = Object.keys(FRAMES).map(f => `<button data-frame="${f}" class="${f === view.frame ? "on" : ""}" aria-pressed="${f === view.frame}">${f}</button>`).join("");
  $("#hint").textContent = FRAMES[view.frame][1];
}
$("#frames").addEventListener("click", e => {
  if (e.target.dataset.frame) { view.frame = e.target.dataset.frame; renderFrames(); loadChart(); }
});

async function loadChart() {
  const mine = ++request;
  const { symbol, frame } = view;
  $("#stock").textContent = symbol;
  $("#chart-error").hidden = true;
  renderWatch();
  $("#source").textContent = "Loading prices…";
  let d;
  try {
    d = await api(`/api/chart?symbol=${encodeURIComponent(symbol)}&frame=${encodeURIComponent(frame)}`);
  } catch (e) {
    if (mine !== request) return;
    $("#chart-error").textContent = e.message;
    $("#chart-error").hidden = false;
    $("#source").textContent = "";
    return;
  }
  if (mine !== request) return;
  view.rows = d.candles;
  view.labels = Object.fromEntries(d.candles.map(c => [c.time, c.label]));
  candles.setData(d.candles);
  volume.setData(d.candles.map(c => ({ time: c.time, value: c.volume, color: (c.close >= c.open ? UP : DOWN) + "99" })));
  view.lines.forEach(l => candles.removePriceLine(l));
  view.lines = [[d.ceiling, "Ceiling", css("--down-text")], [d.floor, "Floor", css("--floor")]].filter(x => x[0] != null)
    .map(([price, title, color]) => candles.createPriceLine({ price, title, color, lineWidth: 2, lineStyle: 2, axisLabelVisible: true }));
  const n = d.candles.length, show = FRAMES[frame][0];
  chart.timeScale().setVisibleLogicalRange({ from: Math.max(-1, n - show), to: n + 1 });
  const last = d.candles[n - 1], change = last.close - last.open;
  $("#price").textContent = inr(last.close);
  $("#change").innerHTML = `<span class="${change >= 0 ? "pos" : "neg"}">${change >= 0 ? "Up" : "Down"} ${inr(Math.abs(change))} in the latest ${frame === "Half-year" ? "half-year" : frame.toLowerCase()}</span>`;
  readout(last);
  $("#view-title").textContent = d.view.title;
  $("#view-text").textContent = d.view.text;
  $("#ceiling").textContent = inr(d.ceiling);
  $("#floor").textContent = inr(d.floor);
  $("#source").textContent = `Prices from ${d.source}, latest candle ${last.label}. Scroll or drag the chart to see older candles.${d.note ? " " + d.note : ""}`;
}

function openStock(sym) {
  view.symbol = sym.trim().toUpperCase();
  $("#suggest").innerHTML = "";
  $("#q").value = "";
  loadChart();
}
$("#search").addEventListener("submit", e => {
  e.preventDefault();
  const first = $("#suggest button");
  const typed = $("#q").value.trim();
  if (first && typed.includes(" ")) openStock(first.dataset.sym);
  else if (typed) openStock(typed);
});
let timer, searchRequest = 0;
$("#q").addEventListener("input", () => {
  clearTimeout(timer);
  const q = $("#q").value.trim(), mine = ++searchRequest;
  timer = setTimeout(async () => {
    const res = q.length < 2 ? { results: [] } : await api(`/api/search?q=${encodeURIComponent(q)}`).catch(() => ({ results: [] }));
    if (mine === searchRequest) $("#suggest").innerHTML = res.results.map(r => `<button type="button" data-sym="${esc(r.symbol)}">${esc(r.symbol)} <span class="muted">${esc(r.name)}</span></button>`).join("");
  }, 300);
});
$("#suggest").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (b) openStock(b.dataset.sym);
});

/* ---------- robot's picks ---------- */
let picks = null, picksAll = false, picksTimer;
async function loadPicks() {
  clearTimeout(picksTimer);
  try {
    const p = await api("/api/picks");
    if (p.working && !p.rows) {
      $("#picks-note").textContent = "Looking through about 50 big NSE stocks with the robot's buying rules. This takes up to a minute the first time…";
      picksTimer = setTimeout(loadPicks, 4000);
      return;
    }
    picks = p;
    renderPicks();
    if (p.working) picksTimer = setTimeout(loadPicks, 8000);
  } catch (e) { $("#picks-note").textContent = e.message; }
}
function renderPicks() {
  if (!picks) return;
  const near = picks.rows.filter(r => r.group !== "later"), ready = near.filter(r => r.group === "ready").length;
  const shown = picksAll ? picks.rows : near;
  const others = picks.rows.length - near.length;
  $("#picks-note").textContent = (ready ? `${ready} ready to buy now. ` : "Nothing meets the buying rules today. ")
    + `Looked at ${picks.rows.length} stocks on finished daily candles up to ${picks.as_of}, from ${picks.source}.`
    + (picks.skipped.length ? ` Skipped ${picks.skipped.length} with no prices.` : "")
    + " This is not advice, only what the robot's rules see.";
  const add = r => !owner || !bot ? "" : bot.stocks.includes(r.symbol)
    ? `<button class="add" data-pick-remove="${esc(r.symbol)}" aria-label="Remove ${esc(r.symbol)} from the robot">Robot trades this ✓</button>`
    : `<button class="add dark" data-pick-add="${esc(r.symbol)}">Let the robot trade this</button>`;
  $("#picks-body").innerHTML = shown.length ? shown.map(r => `<div class="pick"><div class="sym"><button class="link" data-pick-open="${esc(r.symbol)}">${esc(r.symbol)}</button><div class="small muted">${inr(r.close)}</div></div>
    <p><span class="tag ${r.group}">${esc(r.title)}</span> ${esc(r.text)}</p>${add(r)}</div>`).join("")
    : `<p class="pick">No stock is near a buy today. The robot will keep waiting; that is normal.</p>`;
  $("#picks-more").hidden = !others;
  $("#picks-more").textContent = picksAll ? "Show only the near ones" : `Show all ${picks.rows.length}`;
}
$("#picks-more").addEventListener("click", () => { picksAll = !picksAll; renderPicks(); });
$("#picks-body").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.pickOpen) { openStock(b.dataset.pickOpen); $("#chart").scrollIntoView({ behavior: "smooth", block: "center" }); }
  if (b.dataset.pickAdd) save({ stocks: [...bot.stocks, b.dataset.pickAdd] });
  if (b.dataset.pickRemove) save({ stocks: bot.stocks.filter(x => x !== b.dataset.pickRemove) });
});

/* ---------- robot ---------- */
let bot = null;
const MODES = [
  ["practice", "Practice", "Pretend money only. Nothing is sent to your broker."],
  ["ask", "Ask me first", "It suggests trades and waits for Approve. Pretend money, unless you switch on real orders below."],
  ["auto", "Automatic (locked)", "Would trade on its own. Locked for safety: every real order needs your approval."],
];

const LIMITS = [
  ["daily_loss_pct", "Most it can lose in one day", [2, 3, 5].map(p => [p, p + "%", s => whole(s.money * p / 100)])],
  ["max_trades_per_day", "New trades in one day", [[1, "1", () => "Slowest"], [2, "2", () => "Steady"], [3, "3", () => "Busier"]]],
  ["max_open", "Trades open at once", [[3, "3", () => "Fewer stocks"], [5, "5", () => "Balanced"], [8, "8", () => "More stocks"]]],
];

function setBot(s) { bot = s; renderBot(); }
const save = patch => api("/api/robot/settings", patch).then(setBot);

function renderWatch() {
  if (!bot) return;
  const on = bot.stocks.includes(view.symbol);
  $("#watch").textContent = on ? "Robot can trade this. Remove" : "Let the robot trade this";
  $("#watch").className = "wide " + (on ? "" : "dark");
}
$("#watch").addEventListener("click", () => {
  const on = bot.stocks.includes(view.symbol);
  save({ stocks: on ? bot.stocks.filter(x => x !== view.symbol) : [...bot.stocks, view.symbol] });
});

function renderBot() {
  const s = bot, cap = s.money * s.risk_pct / 100, list = s.stocks.join(", ") || "no stocks yet";
  $("#robot-status").innerHTML = `<span class="dot ${s.paused ? "off" : ""}"></span>${s.paused ? "Robot stopped" : s.live ? "Real orders on" : s.mode === "ask" ? "Robot asking first" : "Robot practising"}`;
  $("#rule-title").textContent = s.paused ? "The robot is stopped" : "Your robot, in one sentence";
  const verb = s.live ? "will suggest trades and send a real order to Zerodha only when you confirm it" : s.mode === "ask" ? "will suggest trades and wait for your approval" : "will practise with pretend money";
  $("#rule-text").textContent = s.paused ? "It will not suggest or make any trades until you press Start."
    : `It ${verb}, using up to ${whole(s.money)} on ${list}, and aims to risk at most ${whole(cap)} on one trade, ${whole(s.money * s.daily_loss_pct / 100)} in one day, with at most ${s.max_trades_per_day} new trade${s.max_trades_per_day === 1 ? "" : "s"} a day.`;
  $("#pause").textContent = s.paused ? "Start the robot" : "Stop everything";
  $("#modes").innerHTML = MODES.map(([id, title, text]) => `<button class="option ${s.mode === id ? "picked" : ""}" data-mode="${id}" aria-pressed="${s.mode === id}" ${id === "auto" ? "disabled" : ""}><b>${title}</b><span>${text}</span></button>`).join("");
  if (document.activeElement !== $("#money")) $("#money").value = Math.round(s.money);
  $("#risks").innerHTML = [[0.5, "Very careful"], [1, "Careful"], [2, "Bolder"]].map(([p, t]) => `<button class="option ${s.risk_pct === p ? "picked" : ""}" data-risk="${p}" aria-pressed="${s.risk_pct === p}"><b>${t}</b><span>${p}% = ${whole(s.money * p / 100)}</span></button>`).join("");
  $("#limits").innerHTML = LIMITS.map(([key, title, options]) => `<div class="limit"><h3>${title}</h3><div class="row">${options.map(([v, label, note]) =>
    `<button class="option ${s[key] === v ? "picked" : ""}" data-limit="${key}" data-value="${v}" aria-pressed="${s[key] === v}"><b>${label}</b><span>${note(s)}</span></button>`).join("")}</div></div>`).join("");
  const chips = [...new Set([...s.stocks, ...watchlist])];
  $("#stocks").innerHTML = chips.map(k => `<button class="${s.stocks.includes(k) ? "on" : ""}" data-stock="${esc(k)}" aria-pressed="${s.stocks.includes(k)}">${esc(k)}</button>`).join("");
  renderLive();
  renderWatch();
  renderActivity();
  renderPicks();
}

function renderLive() {
  const s = bot, item = (ok, text) => `<li><span class="${ok ? "ok" : "no"}">${ok ? "Done" : "Not yet"}</span>: ${text}</li>`;
  const ready = conn.orders_ready && s.mode === "ask";
  $("#live-body").innerHTML = s.live
    ? `<p class="live-on">Real orders are ON. Each approved trade becomes a real Zerodha order after you type its confirmation.</p>
       <button id="live-off" class="wide">Switch off real orders</button>`
    : `<p>Off. Approved trades use pretend money. To send real orders, all of these are needed:</p>
       <ul class="checklist">${item(conn.kite_keys, "Your own Kite Connect app keys in the .env file (a paid Zerodha plan)")}
       ${item(conn.kite_connected, "Logged in to Zerodha with Connect Zerodha (needed again each day)")}
       ${item(s.mode === "ask", "Ask me first mode, above")}
       <li><span class="no">Check yourself</span>: a static IP address registered with Zerodha. Since 1 April 2026 Zerodha rejects API orders from other addresses.</li></ul>
       <p class="small" style="margin-top:10px">Real orders can lose real money, more than the limit if the price gaps. Try Practice first.</p>
       <div class="confirm-row"><label class="sr" for="live-phrase">Type REAL MONEY to switch on</label><input id="live-phrase" placeholder="Type REAL MONEY" ${ready ? "" : "disabled"}>
       <button id="live-on" class="dark" ${ready ? "" : "disabled"}>Switch on real orders</button></div>`;
}
$("#live-card").addEventListener("click", async e => {
  if (!["live-on", "live-off"].includes(e.target.id)) return;
  $("#live-error").hidden = true;
  try { await save(e.target.id === "live-on" ? { live: true, confirm: $("#live-phrase").value } : { live: false }); }
  catch (err) { $("#live-error").textContent = err.message; $("#live-error").hidden = false; }
});
$("#pause").addEventListener("click", () => save({ paused: !bot.paused }));
$("#modes").addEventListener("click", e => { const b = e.target.closest("[data-mode]"); if (b && !b.disabled) save({ mode: b.dataset.mode }); });
$("#risks").addEventListener("click", e => { const b = e.target.closest("[data-risk]"); if (b) save({ risk_pct: Number(b.dataset.risk) }); });
$("#limits").addEventListener("click", e => { const b = e.target.closest("[data-limit]"); if (b) save({ [b.dataset.limit]: Number(b.dataset.value) }); });
$("#stocks").addEventListener("click", e => {
  const k = e.target.dataset.stock;
  if (k) save({ stocks: bot.stocks.includes(k) ? bot.stocks.filter(x => x !== k) : [...bot.stocks, k] });
});
$("#money").addEventListener("change", async () => {
  const v = Number($("#money").value.replace(/[^0-9.]/g, ""));
  $("#money-error").hidden = true;
  try { await save({ money: v }); } catch (e) { $("#money-error").textContent = e.message; $("#money-error").hidden = false; }
});

/* ---------- activity ---------- */
function renderActivity() {
  const s = bot, invested = s.positions.reduce((a, p) => a + p.qty * p.entry, 0);
  const money = s.live || s.positions.some(p => p.live) ? "Money" : "Pretend money";
  $("#totals").innerHTML = `<div><span class="muted small">${money} free within your limit</span><b>${inr(s.money + s.realised - invested)}</b></div><div><span class="muted small">In open trades</span><b>${inr(invested)}</b></div><div><span class="muted small">Closed pretend trades, gain or loss</span><b class="${s.realised >= 0 ? "pos" : "neg"}">${inr(s.realised)}</b></div>`;
  const LIVE = { ordered: "Real order sent, waiting to fill", protected: "Real trade, stop-loss set at Zerodha", unprotected: "Real trade with NO stop-loss: set one in Kite now" };
  $("#open").innerHTML = s.positions.map(p => `<article class="card"><div class="meta"><span>${p.live ? "Ordered" : "Bought"} ${esc(p.date)}</span><span class="${p.status === "unprotected" ? "no" : ""}">${p.live ? LIVE[p.status] || "Real trade" : "Open pretend trade"}</span></div><div class="entry-title">${p.qty} ${esc(p.symbol)} at ${p.live && p.status === "ordered" ? "up to " : ""}${inr(p.entry)}</div><p>Sells near ${inr(p.target)} for a gain, or near ${inr(p.stop)} to limit the loss.</p></article>`).join("");
  $("#pending").innerHTML = s.pending.map(x => `<article class="card"><div class="meta"><span>${esc(x.date)}</span><span>Needs your answer</span></div><div class="entry-title">Suggestion: buy ${x.qty} ${esc(x.symbol)}</div><p>${esc(x.why)}</p>
    <div class="ticket"><div><span>Buy</span><b>${x.qty} ${esc(x.symbol)} at about ${inr(x.entry)}</b></div><div><span>Sell for a gain near</span><b>${inr(x.target)}</b></div><div><span>Sell to limit the loss near</span><b>${inr(x.stop)}</b></div><div><span>Most it could lose</span><b>${inr(x.max_loss)}</b></div></div>
    ${s.live ? `<p class="live-on" style="margin-top:10px">REAL ORDER. Approving sends a limit buy to Zerodha at ${inr(x.entry)} or less. If it fills, a stop-loss and target are set at Zerodha.</p>
    <div class="confirm-row"><label class="sr" for="confirm-${x.id}">Type ${esc("BUY " + x.qty + " " + x.symbol)} to confirm</label><input id="confirm-${x.id}" placeholder="Type BUY ${x.qty} ${esc(x.symbol)}"></div>`
    : `<p class="muted small">Pretend money only.</p>`}
    <p class="muted small">Passed your safety limits. Approve applies only to this exact trade, and the limits are checked again first. A sudden price gap can make the loss bigger.</p>
    <div class="answers"><button class="dark" data-answer="${x.id}" data-approve="1" data-fp="${esc(x.fingerprint)}">${s.live ? "Send real order" : "Approve this trade"}</button><button data-answer="${x.id}">Skip</button></div></article>`).join("");
  $("#log").innerHTML = s.activity.length ? s.activity.map(a => `<article class="card"><div class="meta"><span>${esc(a.when)}</span><span>${esc(a.tag)}</span></div><div class="entry-title">${esc(a.title)}</div><p>${esc(a.why)}</p></article>`).join("")
    : `<section class="card"><p>Nothing yet. Choose stocks on the Robot screen, then press Check now.</p></section>`;
}
$("#pending").addEventListener("click", async e => {
  const b = e.target.closest("[data-answer]");
  if (!b) return;
  try { setBot(await api(`/api/robot/pending/${b.dataset.answer}`, { approve: !!b.dataset.approve, fingerprint: b.dataset.fp, confirm: $(`#confirm-${b.dataset.answer}`)?.value })); }
  catch (err) { $("#check-note").textContent = err.message; setBot(await api("/api/robot")); }
});
$("#check").addEventListener("click", async () => {
  const b = $("#check");
  b.disabled = true;
  $("#check-note").textContent = "Checking…";
  try {
    const r = await api("/api/robot/check", {});
    setBot(r);
    $("#check-note").textContent = r.paused ? "The robot is stopped, so nothing was checked."
      : r.errors.length ? "Could not check: " + r.errors.map(x => x.symbol).join(", ") + ". Everything else is up to date." : "Up to date. Each stock is judged once per finished daily candle.";
  } catch (e) { $("#check-note").textContent = e.message; }
  b.disabled = false;
});

/* ---------- connection ---------- */
let watchlist = [], conn = {}, owner = false;
async function loadStatus() {
  const s = await api("/api/status");
  watchlist = s.watchlist || [];
  owner = s.owner;
  document.body.classList.toggle("visitor", !owner);
  if (!owner) {
    $("#conn").innerHTML = `<a href="/login">Owner login</a>`;
    if (!location.hash.startsWith("#stocks")) show("stocks");
    return;
  }
  conn = { orders_ready: s.orders_ready, kite_keys: s.kite_keys, kite_connected: s.kite.connected };
  const logout = s.auth ? `<form method="post" action="/logout"><button class="link" type="submit">Log out</button></form>` : "";
  $("#conn").innerHTML = (s.kite.connected ? `<span class="dot"></span>Zerodha connected`
    : `<a href="/kite/login" target="_blank" rel="noopener">Connect Zerodha</a>`) + logout;
  if (bot) renderBot();
}
window.addEventListener("focus", () => loadStatus().catch(() => {}));

(async function init() {
  const hash = location.hash.slice(1);
  show(["stocks", "robot", "activity"].includes(hash) ? hash : "stocks");
  renderFrames();
  await loadStatus().catch(() => {});
  if (owner) setBot(await api("/api/robot"));
  loadChart();
  loadPicks();
})();
