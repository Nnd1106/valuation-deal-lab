/* 03 · DCF: interactive unlevered free-cash-flow valuation with reverse DCF. */
(function () {
  'use strict';
  const { D, E, F, COL, $ } = VDL;
  const STEPS = [-0.01, -0.005, 0, 0.005, 0.01];

  function projectionTable(m, r) {
    const fy0 = m.c.annual[m.c.annual.length - 1].fy;
    const rows = r.rows;
    const head = `<tr><th>INR crore</th>${rows.map((x) => `<th>${F.fy(fy0 + x.year)}E</th>`).join('')}</tr>`;
    const line = (label, fn, cls = '') => `<tr class="${cls}"><td>${label}</td>${rows.map((x) => `<td>${fn(x)}</td>`).join('')}</tr>`;
    return `<div class="table-scroll"><table class="data-table"><thead>${head}</thead><tbody>
      ${line('Revenue', (x) => F.crPlain(x.revenue))}
      ${line('growth', (x) => F.pct(x.growth), 'sub')}
      ${line('EBIT', (x) => F.crPlain(x.ebit))}
      ${line('margin', (x) => F.pct(x.ebit_margin), 'sub')}
      ${line('NOPAT (EBIT less tax)', (x) => F.crPlain(x.nopat))}
      ${line('+ Depreciation and amortisation', (x) => F.crPlain(x.da))}
      ${line('− Capital expenditure', (x) => F.crPlain(-x.capex))}
      ${line('capex / revenue', (x) => F.pct(x.capex / x.revenue), 'sub')}
      ${line('− Increase in working capital', (x) => F.crPlain(-x.delta_nwc))}
      ${line('Free cash flow to the firm', (x) => F.crPlain(x.fcff), 'total')}
      ${line('Discount factor', (x) => x.discount_factor.toFixed(3), 'sub')}
      ${line('Present value', (x) => F.crPlain(x.pv_fcff))}
    </tbody></table></div>`;
  }

  function heat(m, base) {
    const a = m.a;
    const waccs = STEPS.map((s) => a.wacc + s);
    const gs = STEPS.map((s) => Math.max(0, a.growth_terminal + s));
    const grid = E.sensitivity(a, 'wacc', waccs, 'growth_terminal', gs);
    const price = m.c.price;
    const body = grid.map((row, i) => `<tr><th scope="row">${F.pct(gs[i], 1)}</th>${row.map((v, j) => {
      if (v === null) return '<td class="na">n.m.</td>';
      const t = Math.max(-1, Math.min(1, (v / price - 1) / 0.5));
      return `<td class="${i === 2 && j === 2 ? 'base' : ''}" style="background:${VDL.divergingBg(t)}" title="WACC ${F.pct(waccs[j], 2)}, terminal growth ${F.pct(gs[i], 1)}: ${F.px(v)} (${F.spct(v / price - 1, 0)} vs price)">${F.px(v)}</td>`;
    }).join('')}</tr>`).join('');
    return `<div class="axis-caption">Columns: WACC · Rows: terminal growth · Cells: value per share</div>
      <table class="heat"><thead><tr><th></th>${waccs.map((w) => `<th scope="col">${F.pct(w, 2)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>
      <div class="legend-row" style="margin-top:10px"><span><span class="swatch" style="background:${VDL.divergingBg(0.8)}"></span>Above the market price</span><span><span class="swatch" style="background:${VDL.divergingBg(0)}"></span>Near the price (${F.px(price)})</span><span><span class="swatch" style="background:${VDL.divergingBg(-0.8)}"></span>Below the market price</span></div>
      <div class="legend-note">Outlined cell: the current case (${F.px(base)}). Full colour is reached at ±50% from the market price.</div>`;
  }

  function paint(m) {
    const c = m.c, a = m.a;
    const r = VDL.dcf(m);
    if (!r) {
      $('dcf-out').innerHTML = `<div class="card"><h2 class="card-title">Model undefined</h2><p class="card-desc" style="margin:0">The WACC (${F.pct(a.wacc, 2)}) must be above terminal growth (${F.pct(a.growth_terminal, 2)}), and the terminal return on new capital must be positive. Adjust the sliders.</p></div>`;
      return;
    }
    const upside = r.per_share / c.price - 1;
    let ig = null, im = null;
    try { ig = E.impliedGrowth(a, c.price); im = E.impliedMargin(a, c.price); } catch (e) { /* keep null */ }
    const fy0 = c.annual[c.annual.length - 1];
    const divs = a.dividends_since_fye.reduce((s, d) => s + d[1], 0);

    $('dcf-out').innerHTML = `
      <div class="card">
        <h2 class="card-title">Result</h2>
        <div class="stat-row">
          ${VDL.statBox('DCF value per share', r.per_share > 0 ? F.px(r.per_share) : 'n.m.', `<span class="${VDL.deltaClass(upside)}">${VDL.arrow(upside)} ${F.spct(upside, 0)}</span> vs ${F.px(c.price)}`, 'lead')}
          ${VDL.statBox('Enterprise value', F.cr(r.enterprise_value), `${F.x(r.enterprise_value / fy0.ebitda)} FY${String(fy0.fy).slice(2)} EBITDA`)}
          ${VDL.statBox('Terminal value share', F.pct(r.terminal_share, 0), `implied ${F.x(r.implied_exit_ev_ebitda)} exit EV/EBITDA`)}
          ${VDL.statBox('Price-implied growth', ig === null ? 'out of range' : F.pct(ig), `model uses ${F.pct(a.growth_start)}`)}
          ${VDL.statBox('Price-implied margin', im === null ? 'out of range' : F.pct(im), `model uses ${F.pct(a.margin_target)}`)}
        </div>
        <div class="grid-2">
          <div>
            <div class="axis-caption">Free cash flow to the firm, INR crore</div>
            <div class="chart-wrap short"><canvas id="dcf-fcff" role="img" aria-label="Projected free cash flow to the firm for each forecast year"></canvas></div>
          </div>
          <div>
            <div class="axis-caption">From enterprise value to equity value, INR crore</div>
            <div class="chart-wrap short"><canvas id="dcf-bridge" role="img" aria-label="Waterfall from present value of cash flows to equity value"></canvas></div>
          </div>
        </div>
        <p class="legend-note">Equity value at the ${F.date(fy0.period_end)} balance sheet is ${F.cr(r.equity_value)}, or ${F.px(r.per_share_fye)} per share on ${F.num(a.shares, 1)} crore shares.
          It is then rolled forward ${a.years_since_fye.toFixed(2)} years to the valuation date at the ${F.pct(a.cost_equity, 2)} cost of equity${divs > 0 ? `, less ₹${F.num(divs, 1)} of dividends paid since` : ''}: <strong style="color:var(--text-primary)">${F.px(r.per_share)}</strong>.</p>
      </div>
      <div class="card">
        <h2 class="card-title">Forecast</h2>
        ${projectionTable(m, r)}
        <p class="legend-note">Terminal value at the end of ${F.fy(fy0.fy + a.n_years)}: next-year NOPAT ${F.cr(r.terminal.nopat_next)} × (1 − g ÷ RONIC = ${F.pct(1 - r.terminal.reinvestment_rate, 0)}) ÷ (WACC − g) = ${F.cr(r.terminal.value)}.
          RONIC used: ${F.pct(r.ronic_used, 2)}${a.ronic_tied ? ' (equal to WACC, so growth beyond the horizon adds no value)' : ''}. ${a.mid_year ? 'Mid-year discounting.' : 'End-of-year discounting.'}</p>
      </div>
      <div class="card">
        <h2 class="card-title">Sensitivity: WACC and terminal growth</h2>
        ${heat(m, r.per_share)}
      </div>`;

    const fyLabels = r.rows.map((x) => F.fy(fy0.fy + x.year) + 'E');
    VDL.chart('dcf-fcff', {
      type: 'bar',
      data: { labels: fyLabels, datasets: [{ data: r.rows.map((x) => x.fcff), backgroundColor: COL.s1, borderRadius: 3, maxBarThickness: 30 }] },
      options: {
        maintainAspectRatio: false,
        scales: { x: VDL.axis({ grid: { display: false }, ticks: { color: COL.ink2, font: { size: 10 }, maxRotation: 0 } }), y: VDL.axis({ ticks: { color: COL.muted, callback: (v) => F.crPlain(v) } }) },
        plugins: { tooltip: { callbacks: { label: (ctx) => { const x = r.rows[ctx.dataIndex]; return [`FCFF ${F.cr(x.fcff)}`, `Revenue ${F.cr(x.revenue)} (${F.spct(x.growth)})`, `EBIT margin ${F.pct(x.ebit_margin)}`, `Present value ${F.cr(x.pv_fcff)}`]; } } } },
      },
    });
    const steps = [
      { label: 'PV of FCFF', value: r.pv_explicit, kind: 'total' },
      { label: 'PV of TV', value: r.pv_terminal, kind: 'delta' },
      { label: 'EV', value: r.enterprise_value, kind: 'total' },
      { label: 'Cash', value: a.cash, kind: 'delta' },
      { label: 'Investments', value: a.lt_investments, kind: 'delta' },
      { label: 'Debt', value: -a.debt, kind: 'delta' },
    ];
    if (a.minority > 0) steps.push({ label: 'Minorities', value: -a.minority, kind: 'delta' });
    steps.push({ label: 'Equity', value: r.equity_value, kind: 'total' });
    VDL.waterfallChart('dcf-bridge', steps, (v) => {
      const abs = Math.abs(v);
      return (v < 0 ? '−' : '') + (abs >= 1e5 ? (abs / 1e5).toFixed(2) + 'L' : abs >= 1e3 ? (abs / 1e3).toFixed(1) + 'k' : abs.toFixed(0));
    });
  }

  function build(host, m) {
    const c = m.c, base = c.dcf.assumptions;
    const fy0 = c.annual[c.annual.length - 1];
    host.innerHTML = `
      <p class="section-intro">
        A ten-year unlevered DCF for <strong>${VDL.esc(c.name)}</strong>, starting from ${F.fy(fy0.fy)} actuals. Growth holds, then fades to terminal growth; the margin
        reverts to the company's own average; growth capex shrinks as growth slows; and the terminal value uses the value-driver formula, so
        terminal growth has to be paid for with reinvestment. The starting values are <strong>mechanical defaults derived from history, not forecasts</strong>:
        move the sliders to express your own view and watch what it is worth.
      </p>
      <div class="panel-grid">
        <div class="card">
          <h2 class="card-title">Assumptions</h2>
          <div class="btn-group" style="margin-bottom:16px" role="group" aria-label="Scenario presets">
            <button type="button" class="btn" data-scn="bear">Bear</button>
            <button type="button" class="btn" data-scn="base">Base (reset)</button>
            <button type="button" class="btn" data-scn="bull">Bull</button>
          </div>
          <div id="dcf-controls"></div>
          <label class="check-row"><input type="checkbox" id="dcf-tied"> After year ${base.n_years}, new investment earns only the cost of capital (RONIC = WACC)</label>
          <div id="dcf-ronic" style="margin-top:14px"></div>
          <label class="check-row"><input type="checkbox" id="dcf-mid"> Mid-year discounting</label>
          <p class="legend-note">Bear and Bull move starting growth by 3 points, the target margin by 2 points and WACC by half a point from the default case.</p>
        </div>
        <div class="stack" id="dcf-out"></div>
      </div>`;

    const a = m.a;
    const refresh = () => { paint(m); VDL.renderKpis(); };
    const host2 = $('dcf-controls');
    VDL.slider(host2, { label: 'Starting revenue growth', min: -0.05, max: 0.30, step: 0.0025, value: a.growth_start, fmt: (v) => F.pct(v, 2),
      hint: `Default: ${c.annual.length - 1}-year revenue CAGR (${F.pct(c.history.revenue_cagr)}), bounded to between terminal growth and 15%.`, onInput: (v) => { a.growth_start = v; refresh(); } });
    VDL.slider(host2, { label: 'Years at that growth before the fade', min: 0, max: 9, step: 1, value: a.high_growth_years, fmt: (v) => `${v} yrs`,
      onInput: (v) => { a.high_growth_years = v; refresh(); } });
    VDL.slider(host2, { label: 'Terminal growth', min: 0.02, max: 0.07, step: 0.0025, value: a.growth_terminal, fmt: (v) => F.pct(v, 2),
      hint: `Capped by default at the risk-free rate (${F.pct(c.cost.risk_free, 2)}).`, onInput: (v) => { a.growth_terminal = v; refresh(); } });
    VDL.slider(host2, { label: 'Steady-state EBIT margin', min: 0.02, max: 0.60, step: 0.0025, value: a.margin_target, fmt: (v) => F.pct(v, 2),
      hint: `Last year ${F.pct(a.margin_start)}; default target is the own ${c.annual.length}-year average. Reached in ${a.margin_converge_years} years.`, onInput: (v) => { a.margin_target = v; refresh(); } });
    VDL.slider(host2, { label: 'WACC', min: 0.06, max: 0.18, step: 0.0005, value: a.wacc, fmt: (v) => F.pct(v, 2),
      hint: 'Built on the Cost of Capital tab. Moving it here overrides that build.', onInput: (v) => { a.wacc = v; m.waccManual = true; refresh(); } });
    VDL.slider(host2, { label: 'Steady-state capex / revenue', min: 0, max: 0.25, step: 0.001, value: a.capex_pct_terminal, fmt: (v) => F.pct(v, 1),
      hint: `History ${F.pct(a.capex_pct)} against depreciation of ${F.pct(a.da_pct)}. Growth capex shrinks as growth fades.`, onInput: (v) => { a.capex_pct_terminal = v; refresh(); } });
    const ronic = VDL.slider($('dcf-ronic'), { label: 'Terminal return on new capital (RONIC)', min: 0.05, max: 0.40, step: 0.0025, value: a.ronic_tied ? a.wacc : a.terminal_ronic, fmt: (v) => F.pct(v, 2),
      hint: 'Above WACC means the company keeps a competitive advantage on new investment for ever.', onInput: (v) => { a.terminal_ronic = v; refresh(); } });
    const tied = $('dcf-tied'), mid = $('dcf-mid');
    tied.checked = a.ronic_tied; mid.checked = a.mid_year; ronic.disable(a.ronic_tied);
    tied.addEventListener('change', () => {
      a.ronic_tied = tied.checked;
      if (!tied.checked) { a.terminal_ronic = Math.max(a.wacc, a.terminal_ronic); ronic.set(a.terminal_ronic); }
      ronic.disable(tied.checked);
      refresh();
    });
    mid.addEventListener('change', () => { a.mid_year = mid.checked; refresh(); });

    host.querySelectorAll('[data-scn]').forEach((b) => b.addEventListener('click', () => {
      const fresh = VDL.resetModel(c.ticker);
      const sign = { bear: -1, base: 0, bull: 1 }[b.dataset.scn];
      fresh.a.growth_start = Math.max(base.growth_terminal, base.growth_start + sign * 0.03);
      fresh.a.margin_target = Math.max(0.01, base.margin_target + sign * 0.02);
      fresh.a.wacc = base.wacc - sign * 0.005;
      fresh.waccManual = sign !== 0;
      VDL.show();
    }));
    paint(m);
  }

  VDL.tabs.dcf = { build };
})();
