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
  if (tab === "activity" && typeof loadQuotes === "function" && bot) loadQuotes();
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
  closeSuggest();
  $("#q").value = "";
  loadChart();
}

/* search dropdown: instant matches from stocks the page already knows, then Yahoo's search */
let suggestions = [], active = -1, timer, searchRequest = 0, searching = false;
const known = () => {
  const price = Object.fromEntries((picks?.rows || []).map(r => [r.symbol, r.close]));
  return [...new Set([...watchlist, ...(picks?.rows || []).map(r => r.symbol), ...(bot?.stocks || [])])].map(sym => ({ symbol: sym, name: "", price: price[sym] }));
};
function closeSuggest() {
  suggestions = []; active = -1; searching = false;
  $("#suggest").hidden = true; $("#suggest").innerHTML = "";
  $("#q").setAttribute("aria-expanded", "false"); $("#q").removeAttribute("aria-activedescendant");
}
function renderSuggest() {
  const q = $("#q").value.trim();
  if (!q) return closeSuggest();
  const items = suggestions.map((r, i) => `<li id="opt-${i}" role="option" class="${i === active ? "active" : ""}" aria-selected="${i === active}" data-sym="${esc(r.symbol)}">
      <b>${esc(r.symbol)}</b><span class="muted">${esc(r.name)}</span>${r.price != null ? `<span class="opt-price">${inr(r.price)}</span>` : ""}</li>`).join("");
  const tail = searching ? `<li class="note" aria-live="polite">Searching…</li>` : suggestions.length ? "" : `<li class="note">No matching NSE stock. Press Show to try "${esc(q.toUpperCase())}" anyway.</li>`;
  $("#suggest").innerHTML = items + tail;
  $("#suggest").hidden = false;
  $("#q").setAttribute("aria-expanded", "true");
  if (active >= 0) { $("#q").setAttribute("aria-activedescendant", "opt-" + active); $("#opt-" + active)?.scrollIntoView({ block: "nearest" }); }
  else $("#q").removeAttribute("aria-activedescendant");
}
function merge(local, remote) {
  const seen = new Map(local.map(r => [r.symbol, r]));
  remote.forEach(r => seen.set(r.symbol, { ...(seen.get(r.symbol) || {}), symbol: r.symbol, name: r.name }));
  return [...seen.values()].slice(0, 10);
}
$("#q").addEventListener("input", () => {
  clearTimeout(timer);
  const q = $("#q").value.trim(), Q = q.toUpperCase(), mine = ++searchRequest;
  if (!q) return closeSuggest();
  const local = known().filter(r => r.symbol.startsWith(Q)).sort((a, b) => a.symbol.length - b.symbol.length || a.symbol.localeCompare(b.symbol)).slice(0, 6);
  suggestions = local; active = local.length ? 0 : -1; searching = q.length >= 2;
  renderSuggest();
  if (q.length < 2) return;
  timer = setTimeout(async () => {
    const res = await api(`/api/search?q=${encodeURIComponent(q)}`).catch(() => ({ results: [] }));
    if (mine !== searchRequest) return;
    suggestions = merge(local, res.results.map(r => ({ symbol: r.symbol, name: r.name })));
    searching = false;
    if (active < 0 && suggestions.length) active = 0;
    renderSuggest();
  }, 250);
});
$("#q").addEventListener("keydown", e => {
  if ($("#suggest").hidden) return;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!suggestions.length) return;
    active = (active + (e.key === "ArrowDown" ? 1 : -1) + suggestions.length) % suggestions.length;
    renderSuggest();
  } else if (e.key === "Escape") { e.preventDefault(); closeSuggest(); }
});
$("#q").addEventListener("focus", () => { if ($("#q").value.trim()) $("#q").dispatchEvent(new Event("input")); });
$("#search").addEventListener("submit", e => {
  e.preventDefault();
  const typed = $("#q").value.trim();
  if (active >= 0 && suggestions[active]) openStock(suggestions[active].symbol);
  else if (typed) openStock(typed);
});
$("#suggest").addEventListener("mousedown", e => {
  const li = e.target.closest("[data-sym]");
  if (li) { e.preventDefault(); openStock(li.dataset.sym); }
});
// clicks inside the search form (including the click Enter makes on Show) must not clear the choice first
document.addEventListener("click", e => { if (!e.target.closest("#search")) closeSuggest(); });

/* ---------- robot's picks ---------- */
let picks = null, picksAll = false, picksTimer;
async function loadPicks() {
  clearTimeout(picksTimer);
  picksTimer = null;
  try {
    const p = await api("/api/picks");
    if (p.working && !p.rows) {
      $("#picks-note").textContent = "Looking through about 50 big NSE stocks with the robot's buying rules. This takes up to a minute the first time…";
      picksTimer = setTimeout(loadPicks, 4000);
      return;
    }
    picks = p;
    renderPicks();
    renderGrid();
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

/* ---------- budget grid (Robot tab) ---------- */
let gridFilter = "near";
const pct = (v, digits = 1) => (v >= 0 ? "" : "−") + Math.abs(v).toFixed(digits) + "%";
function sizeFor(r) {
  // the same sizing the robot uses when it buys: loss at the stop within your limit, and only money that is free
  const free = bot.money + bot.realised - bot.positions.reduce((a, p) => a + p.qty * p.entry, 0);
  const per = r.entry - r.stop, riskMoney = bot.money * bot.risk_pct / 100;
  const qty = per > 0 ? Math.floor(Math.min(riskMoney / per, Math.max(free, 0) / r.entry)) : 0;
  const why = qty > 0 ? "" : r.entry > free ? "One share costs more than your free money" : "Even 1 share risks more than your loss limit";
  return { qty, cost: qty * r.entry, why, free };
}
function renderGrid() {
  if (!bot || !$("#grid")) return;
  $("#grid-filter").innerHTML = [["near", "Near a buy"], ["plan", "All with a plan"], ["mine", "Robot's stocks"]]
    .map(([k, t]) => `<button class="${gridFilter === k ? "on" : ""}" data-filter="${k}" aria-pressed="${gridFilter === k}">${t}</button>`).join("");
  if (!picks) { $("#grid").innerHTML = ""; $("#grid-note").textContent = "Working out the suggestions…"; return; }
  const bySym = Object.fromEntries([...picks.skipped.map(x => [x.symbol, { symbol: x.symbol, group: "later", title: "No prices", score: 998, text: "No prices could be found for it." }]),
    ...picks.rows.map(r => [r.symbol, r])]);
  // "Robot's stocks" lists every chosen stock, even one with no buy plan today, so each choice shows up at once
  let rows = gridFilter === "mine"
    ? bot.stocks.map(sym => bySym[sym] || { symbol: sym, group: "later", title: "Checking", score: 999, text: "Being looked at now. Its numbers appear in a minute." })
    : picks.rows.filter(r => r.entry != null && (gridFilter === "plan" || r.group !== "later"));
  rows = rows.map(r => r.entry == null ? { ...r, noPlan: true }
    : { ...r, gainPct: r.target ? (r.target - r.entry) / r.entry * 100 : null, lossPct: (r.entry - r.stop) / r.entry * 100, awayPct: (r.close - r.entry) / r.close * 100, size: sizeFor(r) });
  const key = { near: r => r.score, gain: r => -(r.gainPct ?? -99), loss: r => r.lossPct, ratio: r => -((r.gainPct ?? 0) / r.lossPct) }[$("#grid-sort").value];
  rows.sort((a, b) => (a.noPlan - b.noPlan) || (a.noPlan ? a.symbol.localeCompare(b.symbol) : key(a) - key(b)));
  const most = Math.max(1, ...rows.filter(r => !r.noPlan).map(r => r.size.cost / bot.money * 100));
  const addBtn = r => { const on = bot.stocks.includes(r.symbol); return `<td><button class="${on ? "" : "dark"}" data-grid-${on ? "remove" : "add"}="${esc(r.symbol)}">${on ? "Remove" : "Add"}</button></td>`; };
  const name = r => `<td><button class="link" data-pick-open="${esc(r.symbol)}">${esc(r.symbol)}</button><small><span class="tag ${r.group}">${esc(r.title)}</span></small></td>`;
  $("#grid").innerHTML = `<thead><tr><th scope="col">Stock</th><th scope="col">Price now</th><th scope="col">Robot buys near</th><th scope="col">Gain at target</th><th scope="col">Loss at stop</th><th scope="col">Shares</th><th scope="col">Uses of your money</th><th scope="col"><span class="sr">Add or remove</span></th></tr></thead><tbody>`
    + (rows.length ? rows.map(r => {
      if (r.noPlan) return `<tr class="no-plan">${name(r)}<td>${r.close == null ? "—" : inr(r.close)}</td>
        <td colspan="5" class="reason">No buy plan today. ${esc(r.text)} The robot keeps watching and buys only if its rules are met.</td>${addBtn(r)}</tr>`;
      const z = r.size, share = z.cost / bot.money * 100;
      return `<tr>${name(r)}
        <td>${inr(r.close)}</td>
        <td>${inr(r.entry)}<small>${r.awayPct > 0.05 ? pct(r.awayPct) + " below now" : "at today's price"}</small></td>
        <td class="gain">${r.gainPct == null ? "—" : "+" + pct(r.gainPct)}<small>${r.target ? inr(r.target) + (z.qty ? " · +" + whole(z.qty * (r.target - r.entry)) : "") : ""}</small></td>
        <td class="loss">−${pct(r.lossPct).replace("−", "")}<small>${inr(r.stop)}${z.qty ? " · −" + whole(z.qty * (r.entry - r.stop)) : ""}</small></td>
        <td>${z.qty || "0"}<small>${z.qty ? whole(z.cost) : esc(z.why)}</small></td>
        <td><span class="bar" style="width:${Math.round(share / most * 60)}px"></span>${pct(share)}</td>${addBtn(r)}</tr>`;
    }).join("") : `<tr><td colspan="8">${gridFilter === "mine" ? "The robot has no stocks yet. Pick some above, or use Add in “Near a buy”." : "No stocks to show here. Try “All with a plan”."}</td></tr>`) + "</tbody>";
  if (bot.stocks.some(sym => !bySym[sym]) && !picksTimer) picksTimer = setTimeout(loadPicks, 3000);
  $("#grid-note").textContent = `Gain and loss are for the robot's target and safety stop. Shares use ${bot.risk_pct}% of ${whole(bot.money)} as the most one trade may lose, and only your free money (${whole(Math.max(sizeFor({ entry: 1, stop: 0 }).free, 0))}). A price gap can make the loss bigger. Prices up to ${picks.as_of}.`;
}
$("#grid-filter").addEventListener("click", e => { const b = e.target.closest("[data-filter]"); if (b) { gridFilter = b.dataset.filter; renderGrid(); } });
$("#grid-sort").addEventListener("change", renderGrid);
$("#grid").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.pickOpen) { show("stocks"); openStock(b.dataset.pickOpen); }
  if (b.dataset.gridAdd) save({ stocks: [...bot.stocks, b.dataset.gridAdd] });
  if (b.dataset.gridRemove) save({ stocks: bot.stocks.filter(x => x !== b.dataset.gridRemove) });
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

const tradeKey = s => s ? [...s.positions, ...s.pending].map(p => p.symbol).concat(s.stocks).sort().join() : null;
function setBot(s) { const changed = tradeKey(bot) !== tradeKey(s); bot = s; renderBot(); if (changed) loadQuotes(); }
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
  renderGrid();
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
let quotes = { prices: {}, source: null }, quoteTimer;
// Every minute: fetch what the robot did in the background (its own check runs every 15 minutes), then live prices
async function loadQuotes() {
  clearTimeout(quoteTimer);
  if (!owner || !bot) return;
  try { bot = await api("/api/robot"); } catch { /* keep the last copy */ }
  if (bot.positions.length || bot.pending.length || bot.stocks.length) {
    try { quotes = await api("/api/robot/prices"); delete quotes.error; } catch (e) { quotes = { ...quotes, error: e.message }; }
  }
  // keep anything typed in confirmation boxes (REAL MONEY, BUY …) through the redraw
  const typed = [...document.querySelectorAll("#pending input, #live-body input")].map(i => [i.id, i.value, i === document.activeElement]);
  renderBot();
  typed.forEach(([id, value, focused]) => { const i = document.getElementById(id); if (i) { i.value = value; if (focused) i.focus(); } });
  quoteTimer = setTimeout(loadQuotes, 60000);
}
function renderWatching() {
  const s = bot, card = $("#watching-card");
  card.hidden = !s.stocks.length;
  if (!s.stocks.length) return;
  const bySym = Object.fromEntries((picks?.rows || []).map(r => [r.symbol, r]));
  const rows = s.stocks.map(sym => {
    const r = bySym[sym] || {}, live = quotes.prices[sym]?.price, base = r.close;
    const day = live != null && base ? (live - base) / base * 100 : null;
    const gap = live != null && r.entry ? (live - r.entry) / live * 100 : null;
    return `<tr><td>${esc(sym)}<small>${r.title ? `<span class="tag ${r.group}">${esc(r.title)}</span>` : ""}</small></td>
      <td>${live == null ? "—" : inr(live)}<small>${day == null ? "" : `<span class="${day >= 0 ? "gain" : "loss"}">${day >= 0 ? "+" : ""}${pct(day)}</span> vs last close`}</small></td>
      <td>${r.entry ? inr(r.entry) : "—"}<small>${gap == null ? (r.entry ? "" : "no buy plan today") : gap > 0.05 ? pct(gap) + " above it" : "at or below it"}</small></td>
      <td>${r.target ? inr(r.target) : "—"}</td><td>${r.stop ? inr(r.stop) : "—"}</td></tr>`;
  });
  $("#watching").innerHTML = `<thead><tr><th scope="col">Stock</th><th scope="col">Live price</th><th scope="col">Robot buys near</th><th scope="col">Would sell for a gain at</th><th scope="col">Would sell to limit loss at</th></tr></thead><tbody>${rows.join("")}</tbody>`;
}
const signed = v => (v >= 0 ? "+" : "−") + inr(Math.abs(v)).replace("₹", "₹");
function renderActivity() {
  const s = bot, invested = s.positions.reduce((a, p) => a + p.qty * p.entry, 0);
  const now = p => quotes.prices[p.symbol]?.price;
  const valueNow = s.positions.reduce((a, p) => a + p.qty * (now(p) ?? p.entry), 0), open = valueNow - invested;
  const money = s.live || s.positions.some(p => p.live) ? "Money" : "Pretend money";
  $("#totals").innerHTML = `<div><span class="muted small">${money} free within your limit</span><b>${inr(s.money + s.realised - invested)}</b></div>
    <div><span class="muted small">Put into open trades</span><b>${inr(invested)}</b></div>
    <div><span class="muted small">Open trades are worth now</span><b>${inr(valueNow)}</b></div>
    <div><span class="muted small">Open profit or loss</span><b class="${open >= 0 ? "pos" : "neg"}">${signed(open)}${invested ? ` (${pct(open / invested * 100)})` : ""}</b></div>
    <div><span class="muted small">Closed trades, gain or loss</span><b class="${s.realised >= 0 ? "pos" : "neg"}">${signed(s.realised)}</b></div>`;
  const LIVE = { ordered: "Real order sent, waiting to fill", protected: "Real trade, stop-loss set at Zerodha", unprotected: "Real trade with NO stop-loss: set one in Kite now" };
  const q0 = Object.values(quotes.prices)[0];
  $("#live-note").textContent = quotes.error ? quotes.error : (s.positions.length || s.stocks.length) ? (quotes.source ? `Live prices from ${quotes.source}${q0 ? ", at " + new Date(q0.time).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : ""}. Updates every minute.` : "Getting live prices…") : "";
  renderWatching();
  const days = d => Math.max(0, Math.round((Date.now() - new Date(d)) / 864e5));
  $("#open").innerHTML = s.positions.length ? s.positions.map(p => {
    const price = now(p), cost = p.qty * p.entry, pl = price == null ? null : (price - p.entry) * p.qty;
    const span = p.target - p.stop, at = price == null ? null : Math.min(100, Math.max(0, (price - p.stop) / span * 100));
    return `<article class="card"><div class="meta"><span>${p.live ? "Ordered" : "Bought"} ${esc(p.date)} · ${days(p.date)} days ago</span><span class="${p.status === "unprotected" ? "no" : ""}">${p.live ? LIVE[p.status] || "Real trade" : "Open pretend trade"}</span></div>
      <div class="between"><div class="entry-title">${esc(p.symbol)} · ${p.qty} shares</div>
      <div class="pl ${pl == null ? "" : pl >= 0 ? "pos" : "neg"}">${pl == null ? "Price unavailable" : `${signed(pl)} (${pct(pl / cost * 100)})`}</div></div>
      <div class="trade-grid">
        <div><span>Bought at</span><b>${inr(p.entry)}</b></div><div><span>Price now</span><b>${price == null ? "—" : inr(price)}</b></div>
        <div><span>Put in</span><b>${inr(cost)}</b></div><div><span>Worth now</span><b>${price == null ? "—" : inr(price * p.qty)}</b></div>
        <div><span>Sells for a gain at</span><b class="gain">${inr(p.target)}</b><span>${price == null ? "" : pct((p.target - price) / price * 100) + " away · +" + whole((p.target - p.entry) * p.qty)}</span></div>
        <div><span>Sells to limit loss at</span><b class="loss">${inr(p.stop)}</b><span>${price == null ? "" : pct((price - p.stop) / price * 100) + " away · −" + whole((p.entry - p.stop) * p.qty)}</span></div>
      </div>
      ${at == null ? "" : `<div class="track" role="img" aria-label="Price is ${Math.round(at)}% of the way from the stop to the target"><i style="left:calc(${at}% - 2px)"></i></div><div class="track-labels"><span>Stop ${inr(p.stop)}</span><span>Target ${inr(p.target)}</span></div>`}
      <p class="muted small" style="margin-top:8px">${p.live ? "Zerodha sells it when a price hits the stop or target." : "Pretend trades are settled on finished daily candles: it sells on the first day the price touches the stop or the target."}</p></article>`;
  }).join("") : `<section class="card"><p class="muted">No open trades yet. The robot buys only when a stock's rules are met${s.mode === "ask" ? ", and in Ask me first mode it waits for you to approve each one here" : ""}.</p></section>`;
  $("#closed-card").hidden = !s.closed.length;
  $("#closed").innerHTML = `<thead><tr><th scope="col">Stock</th><th scope="col">Bought</th><th scope="col">Sold</th><th scope="col">Shares</th><th scope="col">Buy price</th><th scope="col">Sell price</th><th scope="col">Gain or loss</th></tr></thead><tbody>`
    + s.closed.slice(0, 100).map(c => `<tr><td>${esc(c.symbol)}${c.live ? " <small>real</small>" : ""}</td><td>${esc(c.bought)}</td><td>${esc(c.date)}</td><td>${c.qty ?? "—"}</td><td>${c.entry == null ? "—" : inr(c.entry)}</td><td>${c.exit == null ? "—" : inr(c.exit)}</td>
      <td class="${c.gain == null ? "" : c.gain >= 0 ? "gain" : "loss"}">${c.gain == null ? "Check in Kite" : signed(c.gain) + (c.entry && c.qty ? ` (${pct(c.gain / (c.entry * c.qty) * 100)})` : "")}</td></tr>`).join("") + "</tbody>";
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
