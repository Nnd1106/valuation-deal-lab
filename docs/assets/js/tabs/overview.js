/* 01 · Overview: three lenses on value, what the price implies, history. */
(function () {
  'use strict';
  const { D, E, F, COL } = VDL;

  function meter(label, modelValue, impliedValue, modelLabel, fmt) {
    if (impliedValue === null) {
      return `<div class="implied-row"><div class="implied-head"><span>${label}</span><span class="value">outside the tested range</span></div>` +
        `<div class="control-hint">No value of this driver alone reconciles the model to the market price.</div></div>`;
    }
    const lo = Math.min(modelValue, impliedValue, 0);
    const hi = Math.max(modelValue, impliedValue);
    const pad = (hi - lo) * 0.18 || 0.02;
    const min = lo - (lo < 0 ? pad : 0), max = hi + pad;
    const pos = (v) => ((v - min) / (max - min)) * 100;
    const a = pos(Math.min(modelValue, impliedValue)), b = pos(Math.max(modelValue, impliedValue));
    return `<div class="implied-row">
      <div class="implied-head"><span>${label}</span><span class="value">${fmt(impliedValue)} <span style="color:var(--text-muted);font-weight:400">vs ${fmt(modelValue)} ${modelLabel}</span></span></div>
      <div class="meter" role="img" aria-label="${label}: price implies ${fmt(impliedValue)}, ${modelLabel} ${fmt(modelValue)}">
        <div class="track"></div><div class="span" style="left:${a}%;width:${b - a}%"></div>
        <div class="mark hist" style="left:${pos(modelValue)}%"></div><div class="mark implied" style="left:${pos(impliedValue)}%"></div>
      </div>
      <div class="meter-scale"><span>${fmt(min)}</span><span>${fmt(max)}</span></div>
    </div>`;
  }

  function historyTable(c) {
    const rows = c.annual, h = c.history, ltm = c.ltm, bs = c.latest_bs;
    const cols = rows.map((r) => F.fy(r.fy));
    const last = ltm ? `LTM ${F.monthYear(ltm.period_end)}` : null;
    const head = `<tr><th>INR crore</th>${cols.map((x) => `<th>${x}</th>`).join('')}${last ? `<th>${last}</th>` : ''}</tr>`;
    const line = (label, vals, extra, cls = '') =>
      `<tr class="${cls}"><td>${label}</td>${vals.map((v) => `<td>${v}</td>`).join('')}${last ? `<td>${extra === undefined ? '' : extra}</td>` : ''}</tr>`;
    const group = (label) => `<tr class="group"><td colspan="${cols.length + 1 + (last ? 1 : 0)}">${label}</td></tr>`;
    const pctOf = (num, den) => (den ? F.pct(num / den) : '–');
    const growth = [''].concat(h.revenue_growth.map((g) => F.spct(g)));
    const roic = ['–'].concat(h.roic.map((v) => (v === null ? 'n.m.' : F.pct(v))));
    return `<div class="table-scroll"><table class="data-table"><thead>${head}</thead><tbody>
      ${group('Income statement')}
      ${line('Revenue', rows.map((r) => F.crPlain(r.revenue)), ltm ? F.crPlain(ltm.revenue) : '')}
      ${line('growth', growth, '', 'sub')}
      ${line('EBITDA', rows.map((r) => F.crPlain(r.ebitda)), ltm ? F.crPlain(ltm.ebitda) : '')}
      ${line('margin', rows.map((r) => pctOf(r.ebitda, r.revenue)), ltm ? pctOf(ltm.ebitda, ltm.revenue) : '', 'sub')}
      ${line('EBIT (operating)', rows.map((r) => F.crPlain(r.ebit)), ltm ? F.crPlain(ltm.ebit) : '')}
      ${line('margin', rows.map((r) => pctOf(r.ebit, r.revenue)), ltm ? pctOf(ltm.ebit, ltm.revenue) : '', 'sub')}
      ${line('Net income', rows.map((r) => F.crPlain(r.net_income)), ltm ? F.crPlain(ltm.net_income) : '')}
      ${line('Diluted EPS (₹)', rows.map((r) => F.num(r.eps, 1)), F.num(c.trailing.eps, 1))}
      ${group('Cash flow')}
      ${line('Cash from operations', rows.map((r) => F.crPlain(r.cfo)))}
      ${line('Capital expenditure', rows.map((r) => F.crPlain(-r.capex)))}
      ${line('Free cash flow (CFO − capex)', rows.map((r) => F.crPlain(r.cfo - r.capex)))}
      ${line('CFO / EBITDA', h.cash_conversion.map((v) => (v === null ? '–' : F.pct(v, 0))), '', 'sub')}
      ${line('Dividends paid', rows.map((r) => F.crPlain(-r.dividends)))}
      ${group(`Balance sheet${last ? ` (last column: ${F.date(bs.period_end)})` : ''}`)}
      ${line('Cash and short-term investments', rows.map((r) => F.crPlain(r.cash)), F.crPlain(bs.cash))}
      ${line('Long-term financial investments', rows.map((r) => F.crPlain(r.lt_investments)), F.crPlain(bs.lt_investments))}
      ${line('Total debt incl. leases', rows.map((r) => F.crPlain(r.debt)), F.crPlain(bs.debt))}
      ${line('Shareholders\' equity', rows.map((r) => F.crPlain(r.equity)), F.crPlain(bs.equity))}
      ${line('Invested capital', rows.map((r) => F.crPlain(r.invested_capital)), F.crPlain(bs.invested_capital))}
      ${group('Returns')}
      ${line('ROIC (NOPAT / average invested capital)', roic)}
      ${line('Effective tax rate', h.effective_tax.map((v) => (v === null ? '–' : F.pct(v))))}
    </tbody></table></div>`;
  }

  function build(host, m) {
    const c = m.c;
    const r = VDL.dcf(m);
    const value = r ? r.per_share : null;
    const upside = value !== null ? value / c.price - 1 : null;
    const v = c.comps.valuation;
    const peerMid = v.ev_ebitda ? v.ev_ebitda.implied_mid : null;
    const peMid = v.pe ? v.pe.implied_mid : null;
    let ig = null, im = null;
    try { ig = E.impliedGrowth(m.a, c.price); im = E.impliedMargin(m.a, c.price); } catch (e) { /* undefined model */ }

    const direction = upside === null ? '' : upside >= 0 ? 'above' : 'below';
    const story = (ig !== null || im !== null)
      ? `At ${F.px(c.price)} the market is paying for ` +
        (ig !== null ? `revenue growth of <strong>${F.pct(ig)}</strong> a year for the next ${m.a.high_growth_years} years (the last ${c.annual.length - 1} delivered ${F.pct(c.history.revenue_cagr)})` : '') +
        (ig !== null && im !== null ? ', or for ' : '') +
        (im !== null ? `a steady-state EBIT margin of <strong>${F.pct(im)}</strong> (own average: ${F.pct(c.history.avg_ebit_margin)})` : '') +
        `, each with every other assumption held at the model's setting.`
      : 'No single change in growth or margin within the tested range reconciles this model to the market price.';

    const notes = c.flags.map((f) => `<li>${VDL.esc(f)}</li>`)
      .concat(c.warnings.map((w) => `<li class="warn"><strong>Check:</strong> ${VDL.esc(w)}</li>`));

    host.innerHTML = `
      <p class="section-intro">
        <strong>${VDL.esc(c.name)}</strong> · ${VDL.esc(VDL.sectorName[c.sector])}. Three independent lenses on value, then the question that matters more
        than any point estimate: <strong>what does today's price require you to believe?</strong> The DCF here is a deliberately conservative,
        rules-based baseline (history drives the forecast, and growth after year ${m.a.n_years} earns no excess return), so read the gap to market as
        the expectations built into the price, not as a buy or sell call.
      </p>
      <div class="grid-2">
        <div class="stack">
          <div class="card">
            <h2 class="card-title">Three lenses on value (₹ per share)</h2>
            <div class="stat-row">
              ${VDL.statBox('Market price', F.px(c.price), `52-wk ${F.px(c.lo52)} – ${F.px(c.hi52)}`)}
              ${VDL.statBox('DCF baseline', value !== null && value > 0 ? F.px(value) : 'n.m.',
                upside !== null ? `<span class="${VDL.deltaClass(upside)}">${F.spct(upside, 0)}</span> · ${direction} market` : '', 'lead')}
              ${VDL.statBox('Peers: EV/EBITDA median', F.px(peerMid), peerMid ? `<span class="${VDL.deltaClass(peerMid / c.price - 1)}">${F.spct(peerMid / c.price - 1, 0)}</span> vs price` : '')}
              ${VDL.statBox('Peers: P/E median', F.px(peMid), peMid ? `<span class="${VDL.deltaClass(peMid / c.price - 1)}">${F.spct(peMid / c.price - 1, 0)}</span> vs price` : '')}
            </div>
            <div class="btn-group">
              <button type="button" class="btn" data-go="dcf">Open the DCF →</button>
              <button type="button" class="btn" data-go="comps">Open comps →</button>
              <button type="button" class="btn" data-go="field">Football field →</button>
            </div>
          </div>
          <div class="card">
            <h2 class="card-title">What the price implies (reverse DCF)</h2>
            <p class="card-desc">${story}</p>
            ${meter(`Revenue growth, next ${m.a.high_growth_years} years`, m.a.growth_start, ig, 'in the model', (x) => F.pct(x))}
            ${meter('Steady-state EBIT margin', m.a.margin_target, im, 'in the model', (x) => F.pct(x))}
            <div class="legend-row" style="margin-top:12px"><span><span class="swatch" style="background:${COL.ink2}"></span>Model assumption</span><span><span class="swatch" style="background:${COL.s2}"></span>Implied by the market price</span></div>
          </div>
        </div>
        <div class="card">
          <h2 class="card-title">Share price, five years (weekly close)</h2>
          <div class="chart-wrap tall"><canvas id="ov-price" role="img" aria-label="Weekly closing share price of ${VDL.esc(c.name)} over five years, with the DCF baseline value marked"></canvas></div>
          <div class="legend-note">Dashed line: the DCF baseline value under the current assumptions. Prices are split-adjusted traded closes from the scheduled pipeline.</div>
        </div>
      </div>
      <div class="card" style="margin-top:18px">
        <h2 class="card-title">Financial history</h2>
        <p class="card-desc">Standardised from the provider's raw statements: EBIT is operating income before other and investment income; cash, short-term and long-term financial investments are treated as non-operating and valued in the equity bridge instead.</p>
        ${historyTable(c)}
      </div>
      ${notes.length ? `<div class="card" style="margin-top:18px"><h2 class="card-title">Data notes for this company</h2><ul class="note-list">${notes.join('')}</ul></div>` : ''}`;

    host.querySelectorAll('[data-go]').forEach((b) => b.addEventListener('click', () => VDL.go(b.dataset.go)));

    const px = c.prices;
    const lo = Math.min(...px.close, value !== null && value > 0 ? value : Infinity);
    const hi = Math.max(...px.close, value !== null && value > 0 ? value : -Infinity);
    VDL.chart('ov-price', {
      type: 'line',
      data: { labels: px.dates, datasets: [{ data: px.close, borderColor: COL.s1, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, pointHoverBackgroundColor: COL.s1, tension: 0.1 }] },
      options: {
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        scales: {
          x: VDL.axis({ grid: { display: false }, ticks: { color: COL.muted, maxTicksLimit: 6, maxRotation: 0, callback(v) { return this.getLabelForValue(v).slice(0, 4); } } }),
          y: VDL.axis({ suggestedMin: lo * 0.92, suggestedMax: hi * 1.05, ticks: { color: COL.muted, callback: (v) => F.rupees(v) } }),
        },
        plugins: {
          refLine: { value: value !== null && value > 0 ? value : null, label: `DCF baseline ${F.px(value)}` },
          tooltip: { callbacks: { title: (items) => F.date(items[0].label), label: (ctx) => `Close ${F.px(ctx.parsed.y)}` } },
        },
      },
    });
  }

  VDL.tabs.overview = { build };
})();
