from flask import Flask, jsonify, request, render_template_string

app = Flask(__name__)

# ---------- Asset classes ----------
ASSETS = [
    "Large Cap Equity",
    "Mid & Small Cap Equity",
    "Debt Funds / Bonds",
    "Gold",
    "International Equity",
    "Real Estate / REITs",
    "AIF / PMS (Illiquid)",
    "Cash",
]
DEFAULTS = [6.0, 3.0, 5.0, 1.5, 2.0, 2.0, 1.5, 1.0]
LIQUID = ["Large Cap Equity", "Mid & Small Cap Equity", "Debt Funds / Bonds",
          "Gold", "International Equity", "Cash"]
PLEDGEABLE = ["Large Cap Equity", "Mid & Small Cap Equity"]

# ---------- Historical scenarios (approximate peak-to-trough, INR terms) ----------
HISTORICAL = {
    "Global Financial Crisis (2008)": {
        "Large Cap Equity": -0.55, "Mid & Small Cap Equity": -0.70, "Debt Funds / Bonds": 0.05,
        "Gold": 0.25, "International Equity": -0.40, "Real Estate / REITs": -0.30,
        "AIF / PMS (Illiquid)": -0.50, "Cash": 0.0},
    "COVID crash (Feb-Mar 2020)": {
        "Large Cap Equity": -0.38, "Mid & Small Cap Equity": -0.42, "Debt Funds / Bonds": 0.00,
        "Gold": 0.05, "International Equity": -0.28, "Real Estate / REITs": -0.10,
        "AIF / PMS (Illiquid)": -0.35, "Cash": 0.0},
    "Taper tantrum (2013)": {
        "Large Cap Equity": -0.15, "Mid & Small Cap Equity": -0.20, "Debt Funds / Bonds": -0.05,
        "Gold": 0.10, "International Equity": 0.10, "Real Estate / REITs": -0.05,
        "AIF / PMS (Illiquid)": -0.15, "Cash": 0.0},
    "Demonetisation (2016)": {
        "Large Cap Equity": -0.10, "Mid & Small Cap Equity": -0.15, "Debt Funds / Bonds": 0.02,
        "Gold": -0.05, "International Equity": 0.02, "Real Estate / REITs": -0.15,
        "AIF / PMS (Illiquid)": -0.10, "Cash": 0.0},
    "Global rate hikes (2022)": {
        "Large Cap Equity": -0.15, "Mid & Small Cap Equity": -0.20, "Debt Funds / Bonds": -0.02,
        "Gold": 0.05, "International Equity": -0.15, "Real Estate / REITs": -0.05,
        "AIF / PMS (Illiquid)": -0.15, "Cash": 0.0},
}

# ---------- Sliders for the custom shock ----------
SLIDERS = [
    {"id": "lc", "label": "Large cap equity change (%)", "min": -70, "max": 30, "default": -30},
    {"id": "mc", "label": "Mid & small cap equity change (%)", "min": -80, "max": 30, "default": -40},
    {"id": "rate_bps", "label": "Interest rate change (bps)", "min": -300, "max": 500, "default": 200},
    {"id": "gold", "label": "Gold change (%)", "min": -40, "max": 60, "default": 10},
    {"id": "global_eq", "label": "Global equities change in USD (%)", "min": -60, "max": 30, "default": -20},
    {"id": "inr", "label": "Rupee depreciation vs USD (%)", "min": -20, "max": 40, "default": 10},
    {"id": "real_estate", "label": "Real estate change (%)", "min": -50, "max": 20, "default": -15},
    {"id": "aif", "label": "AIF / PMS change (%)", "min": -60, "max": 20, "default": -25},
]


def num(value, default, low, high):
    """Turn user input into a safe number within limits."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, x))


def crore(x):
    sign = "-" if x < 0 else ""
    return f"{sign}₹{abs(x):,.2f} Cr"


def analyse(holdings, shocks, loan, max_ltv):
    rows = []
    before = after = liquid = pledged = 0.0
    for asset in ASSETS:
        value = holdings[asset]
        shock = shocks.get(asset, 0.0)
        pnl = value * shock
        rows.append({"asset": asset, "before": value, "shock": shock * 100,
                     "pnl": pnl, "after": value + pnl})
        before += value
        after += value + pnl
        if asset in LIQUID:
            liquid += value + pnl
        if asset in PLEDGEABLE:
            pledged += value + pnl

    leverage = None
    if loan > 0:
        if pledged <= 0:
            leverage = {"status": "bad", "text": "No pledged equity left to cover the loan."}
        else:
            ltv = loan / pledged * 100
            if ltv > max_ltv:
                shortfall = loan - (max_ltv / 100) * pledged
                leverage = {"status": "bad",
                            "text": f"Margin call: loan-to-value is {ltv:.1f}%, above the {max_ltv:.0f}% "
                                    f"limit. The client must repay or top up about {crore(shortfall)}."}
            else:
                leverage = {"status": "ok",
                            "text": f"Loan-to-value after the shock is {ltv:.1f}%, "
                                    f"within the {max_ltv:.0f}% limit."}

    pnl = after - before
    return {
        "rows": rows, "before": before, "after": after, "pnl": pnl,
        "pct": pnl / before * 100 if before else 0,
        "net_worth": after - loan,
        "liquid": liquid, "liquid_pct": liquid / after * 100 if after > 0 else 0,
        "leverage": leverage,
    }


@app.route("/")
def index():
    return render_template_string(PAGE, inputs=list(zip(ASSETS, DEFAULTS)),
                                  scenarios=list(HISTORICAL), sliders=SLIDERS)


@app.route("/api/stress", methods=["POST"])
def api_stress():
    data = request.get_json(silent=True) or {}
    raw = data.get("holdings") or {}
    holdings = {a: num(raw.get(a), 0.0, 0.0, 1e7) for a in ASSETS}
    total = sum(holdings.values())
    if total <= 0:
        return jsonify({"error": "Enter at least one holding on the left to run a stress test."})

    duration = num(data.get("duration"), 4.0, 0.0, 30.0)
    convexity = num(data.get("convexity"), 30.0, 0.0, 500.0)
    loan = num(data.get("loan"), 0.0, 0.0, 1e7)
    max_ltv = num(data.get("max_ltv"), 50.0, 10.0, 80.0)

    # Custom shock: debt via duration and convexity, international via USD move and rupee
    c_raw = data.get("custom") or {}
    c = {s["id"]: num(c_raw.get(s["id"]), s["default"], s["min"], s["max"]) for s in SLIDERS}
    dy = c["rate_bps"] / 10000
    debt_shock = -duration * dy + 0.5 * convexity * dy ** 2
    intl_shock = (1 + c["global_eq"] / 100) * (1 + c["inr"] / 100) - 1
    custom = {
        "Large Cap Equity": c["lc"] / 100, "Mid & Small Cap Equity": c["mc"] / 100,
        "Debt Funds / Bonds": debt_shock, "Gold": c["gold"] / 100,
        "International Equity": intl_shock, "Real Estate / REITs": c["real_estate"] / 100,
        "AIF / PMS (Illiquid)": c["aif"] / 100, "Cash": 0.0,
    }

    scenario = data.get("scenario")
    if scenario not in HISTORICAL:
        scenario = list(HISTORICAL)[0]

    compare = []
    for name, shocks in list(HISTORICAL.items()) + [("Your custom shock", custom)]:
        r = analyse(holdings, shocks, loan, max_ltv)
        compare.append({"name": name, "pnl": r["pnl"], "pct": r["pct"]})
    historical_only = [x for x in compare if x["name"] in HISTORICAL]
    worst = min(historical_only, key=lambda x: x["pnl"])
    compare.sort(key=lambda x: x["pct"])

    return jsonify({
        "total": total,
        "worst": {"name": worst["name"], "after": total + worst["pnl"],
                  "loss": abs(worst["pnl"]), "pct": abs(worst["pct"])},
        "historical": analyse(holdings, HISTORICAL[scenario], loan, max_ltv),
        "custom": analyse(holdings, custom, loan, max_ltv),
        "debt_shock": debt_shock * 100, "intl_shock": intl_shock * 100,
        "compare": compare,
    })


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>HNI Portfolio Stress Test</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root { --ink:#0F2A3D; --brass:#B08D57; --loss:#B23A3A; --gain:#2E7D5B; --muted:#6B7785;
        --grid:#E3E6EB; --bg:#F7F8FA; --side:#EDEFF3; }
* { box-sizing: border-box; }
body { margin:0; font-family:'IBM Plex Sans', Arial, sans-serif; color:var(--ink); background:var(--bg); }
.layout { display:flex; min-height:100vh; }
aside { width:300px; flex-shrink:0; background:var(--side); padding:28px 22px; }
main { flex:1; min-width:0; padding:40px 48px; max-width:1250px; }
h1, h2 { font-family:'DM Serif Display', Georgia, serif; font-weight:400; }
h1 { font-size:2.6rem; margin:0 0 6px; }
aside h2 { font-size:1.4rem; margin:22px 0 2px; }
aside h2:first-child { margin-top:0; }
.caption { color:var(--muted); font-size:.9rem; }
.field { margin:12px 0; }
.field label { display:block; font-size:.9rem; margin-bottom:4px; }
.field input[type=number], select { width:100%; padding:8px 10px; font:inherit; color:var(--ink);
        border:1px solid #D5DAE1; border-radius:6px; background:#fff; }
input[type=range] { width:100%; accent-color:var(--brass); }
.range-head { display:flex; justify-content:space-between; font-size:.9rem; margin-bottom:2px; }
.range-head b { font-weight:600; }
.hero { border-top:3px solid var(--brass); padding:22px 0 26px; margin-top:22px; }
.hero-figure { font-family:'DM Serif Display', Georgia, serif; font-size:3.4rem; line-height:1.1; margin:6px 0; }
.loss { color:var(--loss); } .gain { color:var(--gain); }
.tabs { display:flex; gap:26px; border-bottom:1px solid var(--grid); margin-bottom:20px; flex-wrap:wrap; }
.tab { background:none; border:none; border-bottom:2px solid transparent; padding:10px 0; font:inherit;
       font-size:1rem; color:var(--ink); cursor:pointer; }
.tab.active { border-color:var(--brass); color:var(--brass); }
.tab:focus-visible, input:focus-visible, select:focus-visible { outline:2px solid var(--brass); outline-offset:2px; }
.panel { display:none; } .panel.active { display:block; }
.cards { display:grid; grid-template-columns:repeat(4, 1fr); gap:14px; margin:16px 0; }
.card { background:#fff; border:1px solid var(--grid); border-left:4px solid var(--brass); border-radius:6px; padding:14px 18px; }
.card .label { font-size:.9rem; color:var(--muted); }
.card .value { font-family:'DM Serif Display', Georgia, serif; font-size:1.9rem; margin-top:4px; }
.card .delta { font-size:.85rem; margin-top:2px; }
.note { padding:13px 18px; border-radius:6px; margin:10px 0; font-size:.95rem; }
.note.info { background:#E4ECF5; } .note.ok { background:#E3F1EA; color:var(--gain); }
.note.bad { background:#F6E3E3; color:var(--loss); }
.sliders { display:grid; grid-template-columns:1fr 1fr; gap:8px 40px; margin-bottom:8px; }
table { width:100%; border-collapse:collapse; background:#fff; font-size:.9rem; margin-top:8px; }
th, td { padding:8px 12px; border-bottom:1px solid var(--grid); text-align:right; }
th:first-child, td:first-child { text-align:left; }
th { color:var(--muted); font-weight:500; }
details { margin-top:6px; } summary { cursor:pointer; color:var(--muted); padding:6px 0; }
@media (max-width: 900px) {
  .layout { flex-direction:column; } aside { width:auto; } main { padding:24px; }
  .cards { grid-template-columns:1fr 1fr; } .sliders { grid-template-columns:1fr; }
  .hero-figure { font-size:2.3rem; }
}
</style>
</head>
<body>
<div class="layout">
  <aside>
    <h2>Client portfolio</h2>
    <div class="caption">Amounts in ₹ crore</div>
    {% for asset, default in inputs %}
    <div class="field">
      <label>{{ asset }}</label>
      <input type="number" class="holding" data-asset="{{ asset }}" min="0" step="0.5" value="{{ default }}">
    </div>
    {% endfor %}

    <h2>Debt and leverage</h2>
    <div class="field"><label>Modified duration of debt (years)</label>
      <input type="number" id="duration" min="0" max="30" step="0.5" value="4"></div>
    <div class="field"><label>Convexity of debt</label>
      <input type="number" id="convexity" min="0" max="500" step="5" value="30"></div>
    <div class="field"><label>Loan against shares (₹ crore)</label>
      <input type="number" id="loan" min="0" step="0.5" value="0"></div>
    <div class="field">
      <div class="range-head"><span>Maximum loan-to-value on pledged equity</span><b id="max_ltv-val">50%</b></div>
      <input type="range" id="max_ltv" min="10" max="80" value="50">
    </div>
  </aside>

  <main>
    <h1>HNI Portfolio Stress Test</h1>
    <div class="caption">Educational tool. Historical shocks are rough approximations of Indian-investor (INR)
      returns; check and edit them before professional use.</div>

    <div class="hero" id="hero"></div>

    <div class="tabs">
      <button class="tab active" data-panel="p-hist">Historical scenarios</button>
      <button class="tab" data-panel="p-custom">Build your own shock</button>
      <button class="tab" data-panel="p-compare">Compare all scenarios</button>
    </div>

    <section class="panel active" id="p-hist">
      <div class="field"><label>Choose a historical crisis</label>
        <select id="scenario">
          {% for s in scenarios %}<option value="{{ s }}">{{ s }}</option>{% endfor %}
        </select>
      </div>
      <div id="hist-out">
        <div class="cards"></div><div class="notes"></div><div class="chart" id="hist-chart"></div>
        <details><summary>See the detailed table</summary><div class="table"></div></details>
      </div>
    </section>

    <section class="panel" id="p-custom">
      <div class="sliders">
        {% for s in sliders %}
        <div class="field">
          <div class="range-head"><span>{{ s.label }}</span><b id="{{ s.id }}-val">{{ s.default }}</b></div>
          <input type="range" class="shock" id="{{ s.id }}" min="{{ s.min }}" max="{{ s.max }}" value="{{ s.default }}">
        </div>
        {% endfor %}
      </div>
      <div class="caption" id="custom-note"></div>
      <div id="custom-out">
        <div class="cards"></div><div class="notes"></div><div class="chart" id="custom-chart"></div>
        <details><summary>See the detailed table</summary><div class="table"></div></details>
      </div>
    </section>

    <section class="panel" id="p-compare">
      <div class="chart" id="compare-chart"></div>
      <div id="compare-table"></div>
    </section>
  </main>
</div>

<script>
var INK = '#0F2A3D', LOSS = '#B23A3A', GAIN = '#2E7D5B', GRID = '#E3E6EB';

function money(x) {
  var s = Math.abs(x).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return (x < 0 ? '-' : '') + '₹' + s + ' Cr';
}
function signed(x, digits) { return (x > 0 ? '+' : '') + x.toFixed(digits); }

function chartLayout(title, height) {
  return {
    title: {text: title, x: 0, font: {family: 'DM Serif Display, Georgia, serif', size: 20, color: INK}},
    height: height, margin: {l: 50, r: 20, t: 60, b: 90},
    font: {family: 'IBM Plex Sans, Arial, sans-serif', color: INK, size: 13},
    paper_bgcolor: 'rgba(0,0,0,0)', plot_bgcolor: 'rgba(0,0,0,0)', showlegend: false,
    yaxis: {gridcolor: GRID, zerolinecolor: '#C9CED6', automargin: true},
    xaxis: {showgrid: false, automargin: true}
  };
}
var CONFIG = {displayModeBar: false, responsive: true};

function gather() {
  var holdings = {};
  document.querySelectorAll('.holding').forEach(function (el) {
    holdings[el.getAttribute('data-asset')] = parseFloat(el.value) || 0;
  });
  var custom = {};
  document.querySelectorAll('.shock').forEach(function (el) { custom[el.id] = parseFloat(el.value); });
  return {
    holdings: holdings, custom: custom,
    duration: parseFloat(document.getElementById('duration').value),
    convexity: parseFloat(document.getElementById('convexity').value),
    loan: parseFloat(document.getElementById('loan').value),
    max_ltv: parseFloat(document.getElementById('max_ltv').value),
    scenario: document.getElementById('scenario').value
  };
}

function renderResult(boxId, chartId, r) {
  var box = document.getElementById(boxId);
  var deltaClass = r.pct < 0 ? 'loss' : 'gain';
  box.querySelector('.cards').innerHTML =
    '<div class="card"><div class="label">Portfolio before</div><div class="value">' + money(r.before) + '</div></div>' +
    '<div class="card"><div class="label">Portfolio after</div><div class="value">' + money(r.after) + '</div>' +
      '<div class="delta ' + deltaClass + '">' + signed(r.pct, 1) + '%</div></div>' +
    '<div class="card"><div class="label">Gain / loss</div><div class="value ' + deltaClass + '">' + money(r.pnl) + '</div></div>' +
    '<div class="card"><div class="label">Net worth after loan</div><div class="value">' + money(r.net_worth) + '</div></div>';

  var notes = '';
  if (r.leverage) notes += '<div class="note ' + r.leverage.status + '">' + r.leverage.text + '</div>';
  if (r.after > 0) notes += '<div class="note info">Money that can be raised within about a week after the shock: ' +
    money(r.liquid) + ' (' + r.liquid_pct.toFixed(0) + '% of the portfolio).</div>';
  box.querySelector('.notes').innerHTML = notes;

  var moves = r.rows.filter(function (x) { return Math.abs(x.pnl) > 1e-9; });
  var measure = ['absolute'], xs = ['Before'], ys = [r.before], text = [money(r.before)];
  moves.forEach(function (m) { measure.push('relative'); xs.push(m.asset); ys.push(m.pnl); text.push(signed(m.pnl, 2)); });
  measure.push('total'); xs.push('After'); ys.push(0); text.push(money(r.after));
  Plotly.react(chartId, [{
    type: 'waterfall', measure: measure, x: xs, y: ys, text: text, textposition: 'outside',
    decreasing: {marker: {color: LOSS}}, increasing: {marker: {color: GAIN}}, totals: {marker: {color: INK}},
    connector: {line: {color: '#C9CED6', dash: 'dot'}}, hoverinfo: 'x+text'
  }], chartLayout('From before to after, asset by asset (₹ Cr)', 470), CONFIG);

  var rows = r.rows.map(function (x) {
    return '<tr><td>' + x.asset + '</td><td>' + x.before.toFixed(2) + '</td><td>' + signed(x.shock, 1) +
      '</td><td>' + signed(x.pnl, 2) + '</td><td>' + x.after.toFixed(2) + '</td></tr>';
  }).join('');
  box.querySelector('.table').innerHTML = '<table><tr><th>Asset class</th><th>Value before (₹ Cr)</th>' +
    '<th>Shock (%)</th><th>Gain / loss (₹ Cr)</th><th>Value after (₹ Cr)</th></tr>' + rows + '</table>';
}

function renderCompare(list) {
  var shown = list.slice().reverse();   // worst at the top of the chart
  Plotly.react('compare-chart', [{
    type: 'bar', orientation: 'h',
    x: shown.map(function (s) { return s.pct; }), y: shown.map(function (s) { return s.name; }),
    marker: {color: shown.map(function (s) { return s.pct < 0 ? LOSS : GAIN; })},
    text: shown.map(function (s) { return signed(s.pct, 1) + '%'; }), textposition: 'outside', hoverinfo: 'y+text'
  }], Object.assign(chartLayout('Which crisis hurts this client most', 430), {
    xaxis: {title: 'Portfolio change (%)', gridcolor: GRID, zerolinecolor: '#C9CED6', automargin: true},
    yaxis: {showgrid: false, automargin: true}, margin: {l: 20, r: 40, t: 60, b: 60}
  }), CONFIG);

  var rows = list.map(function (s) {
    return '<tr><td>' + s.name + '</td><td>' + signed(s.pnl, 2) + '</td><td>' + signed(s.pct, 1) + '</td></tr>';
  }).join('');
  document.getElementById('compare-table').innerHTML =
    '<table><tr><th>Scenario</th><th>Gain / loss (₹ Cr)</th><th>Change (%)</th></tr>' + rows + '</table>';
}

function run() {
  fetch('/api/stress', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(gather())})
    .then(function (res) { return res.json(); })
    .then(function (d) {
      var hero = document.getElementById('hero');
      if (d.error) { hero.innerHTML = '<div class="note bad">' + d.error + '</div>'; return; }
      hero.innerHTML =
        '<div class="caption">Worst historical case for this portfolio: ' + d.worst.name + '</div>' +
        '<div class="hero-figure">' + money(d.total) + ' to <span class="loss">' + money(d.worst.after) + '</span></div>' +
        '<div>A fall of ' + d.worst.pct.toFixed(1) + '%, or ' + money(d.worst.loss) + ' of client wealth.</div>';
      renderResult('hist-out', 'hist-chart', d.historical);
      renderResult('custom-out', 'custom-chart', d.custom);
      document.getElementById('custom-note').textContent =
        'Debt impact from duration and convexity: ' + d.debt_shock.toFixed(2) +
        '%. International equity in rupees: ' + d.intl_shock.toFixed(2) + '%.';
      renderCompare(d.compare);
    })
    .catch(function () {
      document.getElementById('hero').innerHTML =
        '<div class="note bad">Could not reach the server. Refresh the page to try again.</div>';
    });
}

var timer = null;
function schedule() { clearTimeout(timer); timer = setTimeout(run, 150); }

document.querySelectorAll('input, select').forEach(function (el) {
  el.addEventListener('input', function () {
    var label = document.getElementById(el.id + '-val');
    if (label) label.textContent = el.id === 'max_ltv' ? el.value + '%' : el.value;
    schedule();
  });
});

document.querySelectorAll('.tab').forEach(function (tab) {
  tab.addEventListener('click', function () {
    document.querySelectorAll('.tab').forEach(function (t) { t.classList.remove('active'); });
    document.querySelectorAll('.panel').forEach(function (p) { p.classList.remove('active'); });
    tab.classList.add('active');
    var panel = document.getElementById(tab.getAttribute('data-panel'));
    panel.classList.add('active');
    panel.querySelectorAll('.chart').forEach(function (c) { if (c.data) Plotly.Plots.resize(c); });
  });
});

run();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True)
