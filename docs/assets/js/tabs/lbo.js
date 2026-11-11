/* 05 · LBO: illustrative take-private returns on the DCF operating case. */
(function () {
  'use strict';
  const { D, E, F, COL, $ } = VDL;
  const HURDLE = 0.20;

  const entryEv = (m, premium) => m.c.market_cap * (1 + premium) + VDL.netDebtBridge(m.c);

  // The LBO runs on the live DCF operating case, re-based to trailing revenue and margin.
  const SHARED = ['n_years', 'growth_start', 'growth_terminal', 'high_growth_years', 'margin_target',
    'margin_converge_years', 'tax_rate', 'da_pct', 'capex_pct', 'capex_pct_terminal', 'nwc_pct'];

  function syncEntry(m) {
    for (const k of SHARED) m.lbo[k] = m.a[k];
    m.lbo.hold_years = Math.min(m.lbo.hold_years, m.lbo.n_years);
    m.lbo.entry_ev = entryEv(m, m.lboPremium);
    if (m.lboTie) m.lbo.exit_multiple = m.lbo.entry_ev / m.lbo.ebitda_ltm;
  }

  function schedule(r) {
    const rows = r.rows;
    const line = (label, fn, cls = '') => `<tr class="${cls}"><td>${label}</td>${rows.map((x) => `<td>${fn(x)}</td>`).join('')}</tr>`;
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>INR crore</th>${rows.map((x) => `<th>Year ${x.year}</th>`).join('')}</tr></thead><tbody>
      ${line('Revenue', (x) => F.crPlain(x.revenue))}
      ${line('EBITDA', (x) => F.crPlain(x.ebitda))}
      ${line('− Cash interest', (x) => F.crPlain(-x.interest))}
      ${line('− Tax', (x) => F.crPlain(-x.tax))}
      ${line('− Capex', (x) => F.crPlain(-x.capex))}
      ${line('− Increase in working capital', (x) => F.crPlain(-x.delta_nwc))}
      ${line('Cash flow available for debt service', (x) => F.crPlain(x.cfads), 'total')}
      ${line('Mandatory amortisation', (x) => F.crPlain(-x.mandatory), 'sub')}
      ${line('Cash sweep', (x) => F.crPlain(-x.sweep), 'sub')}
      ${line('Senior term loan, year end', (x) => F.crPlain(x.senior_end))}
      ${line('Subordinated notes', (x) => F.crPlain(x.sub_debt))}
      ${rows.some((x) => x.revolver > 0) ? line('Revolver drawn, year end', (x) => F.crPlain(x.revolver)) : ''}
      ${line('Cash, year end', (x) => F.crPlain(Math.max(0, x.cash_end)))}
      ${line('Total debt / EBITDA', (x) => F.x(x.debt_to_ebitda), 'sub')}
      ${line('EBITDA / interest', (x) => F.x(x.interest_cover), 'sub')}
    </tbody></table></div>`;
  }

  function grid(m) {
    const a = m.lbo;
    const premiums = [-0.15, -0.075, 0, 0.075, 0.15].map((d) => Math.max(0, m.lboPremium + d));
    const exits = [-0.2, -0.1, 0, 0.1, 0.2].map((d) => a.exit_multiple * (1 + d));
    const g = E.irrGrid(a, 'exit_multiple', exits, 'entry_ev', premiums.map((p) => entryEv(m, p)));
    const body = g.map((row, i) => `<tr><th scope="row">${F.pct(premiums[i], 1)}</th>${row.map((v, j) => {
      if (v === null) return '<td class="na">n.m.</td>';
      const t = Math.max(-1, Math.min(1, (v - HURDLE) / 0.15));
      return `<td class="${i === 2 && j === 2 ? 'base' : ''}" style="background:${VDL.divergingBg(t)}" title="Premium ${F.pct(premiums[i], 1)}, exit at ${F.x(exits[j])}: IRR ${F.pct(v)}">${F.pct(v)}</td>`;
    }).join('')}</tr>`).join('');
    return `<div class="axis-caption">Columns: exit EV / EBITDA · Rows: offer premium · Cells: sponsor IRR</div>
      <table class="heat"><thead><tr><th></th>${exits.map((x) => `<th scope="col">${F.x(x)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>
      <div class="legend-row" style="margin-top:10px"><span><span class="swatch" style="background:${VDL.divergingBg(0.8)}"></span>Above a ${F.pct(HURDLE, 0)} hurdle</span><span><span class="swatch" style="background:${VDL.divergingBg(0)}"></span>At the hurdle</span><span><span class="swatch" style="background:${VDL.divergingBg(-0.8)}"></span>Below the hurdle</span></div>`;
  }

  function paint(m) {
    const a = m.lbo;
    let r;
    try { r = E.runLbo(a); } catch (e) {
      $('lbo-out').innerHTML = `<div class="card"><h2 class="card-title">Structure not feasible</h2><p class="card-desc" style="margin:0">${VDL.esc(e.message)}. Reduce the debt multiples or raise the offer premium.</p></div>`;
      return;
    }
    const su = r.sources_uses;
    const irrTxt = r.irr === null ? 'n.m.' : F.pct(r.irr);
    $('lbo-out').innerHTML = `
      <div class="card">
        <h2 class="card-title">Sponsor returns</h2>
        <div class="stat-row">
          ${VDL.statBox('IRR', irrTxt, r.irr === null ? 'equity wiped out at exit' : (r.irr >= HURDLE ? 'clears' : 'below') + ` a ${F.pct(HURDLE, 0)} hurdle`, 'lead')}
          ${VDL.statBox('Money multiple', F.x(r.moic, 2), `${a.hold_years}-year hold`)}
          ${VDL.statBox('Equity cheque', F.cr(su.sponsor_equity), `${F.pct(su.equity_pct, 0)} of total uses`)}
          ${VDL.statBox('Entry multiple', F.x(su.entry_multiple), `exit ${F.x(a.exit_multiple)} EV/EBITDA`)}
          ${VDL.statBox('Opening leverage', F.x(su.leverage_x), `closing ${F.x(r.rows[r.rows.length - 1].debt_to_ebitda)} debt/EBITDA`)}
        </div>
        ${r.liquidity_shortfall ? `<p class="card-desc">${VDL.status('warn', 'Liquidity shortfall')} Cash flow does not cover interest, tax, investment and mandatory amortisation in at least one year. The gap is drawn on a revolver at the senior rate, which is included in the returns below; a lender would not sign this structure as it stands.</p>` : ''}
        <div class="grid-2">
          <div>
            <div class="axis-caption">Where the equity gain comes from, INR crore</div>
            <div class="chart-wrap short"><canvas id="lbo-bridge" role="img" aria-label="Value creation bridge from equity invested to exit equity"></canvas></div>
          </div>
          <div>
            <div class="axis-caption">Debt outstanding at each year end, INR crore</div>
            <div class="legend-row"><span><span class="swatch" style="background:${COL.s1}"></span>Senior term loan</span><span><span class="swatch" style="background:${COL.s2}"></span>Subordinated notes</span>${r.liquidity_shortfall ? `<span><span class="swatch" style="background:${COL.s3}"></span>Revolver</span>` : ''}</div>
            <div class="chart-wrap short" style="height:220px"><canvas id="lbo-debt" role="img" aria-label="Senior and subordinated debt outstanding by year"></canvas></div>
          </div>
        </div>
      </div>
      <div class="grid-2">
        <div class="card">
          <h2 class="card-title">Sources and uses at close</h2>
          <div class="table-scroll"><table class="data-table"><thead><tr><th>Uses</th><th>INR crore</th><th>Sources</th><th>INR crore</th></tr></thead><tbody>
            <tr><td>Enterprise value</td><td>${F.crPlain(su.entry_ev)}</td><td style="text-align:left;color:var(--text-primary)">Senior term loan (${F.x(a.senior_x)})</td><td>${F.crPlain(su.senior_debt)}</td></tr>
            <tr><td>Transaction fees (${F.pct(a.fee_pct, 0)})</td><td>${F.crPlain(su.fees)}</td><td style="text-align:left;color:var(--text-primary)">Subordinated notes (${F.x(a.sub_x)})</td><td>${F.crPlain(su.sub_debt)}</td></tr>
            <tr><td></td><td></td><td style="text-align:left;color:var(--text-primary)">Sponsor equity</td><td>${F.crPlain(su.sponsor_equity)}</td></tr>
            <tr class="total"><td>Total uses</td><td>${F.crPlain(su.total_uses)}</td><td style="text-align:left">Total sources</td><td>${F.crPlain(su.total_sources)}</td></tr>
          </tbody></table></div>
          <p class="legend-note">Cash-free, debt-free basis: existing debt is refinanced, and existing cash and financial investments are netted in the enterprise value, so the new structure opens with no cash.</p>
        </div>
        <div class="card">
          <h2 class="card-title">IRR sensitivity</h2>
          ${grid(m)}
        </div>
      </div>
      <div class="card">
        <h2 class="card-title">Cash flow and debt schedule</h2>
        ${schedule(r)}
        <p class="legend-note">Interest is charged on the average senior balance, which makes interest and the cash sweep depend on each other; the engine solves that circularity by iteration. Tax is ${F.pct(a.tax_rate, 2)} of positive pre-tax profit, with interest fully deductible.</p>
      </div>`;

    const at = r.attribution;
    const compact = (v) => { const abs = Math.abs(v); return (v < 0 ? '−' : '') + (abs >= 1e5 ? (abs / 1e5).toFixed(2) + 'L' : abs >= 1e3 ? (abs / 1e3).toFixed(1) + 'k' : abs.toFixed(0)); };
    VDL.waterfallChart('lbo-bridge', [
      { label: 'Equity in', value: su.sponsor_equity, kind: 'total' },
      { label: 'EBITDA growth', value: at.ebitda_growth, kind: 'delta' },
      { label: 'Multiple', value: at.multiple_expansion, kind: 'delta' },
      { label: 'Debt paydown', value: at.deleveraging, kind: 'delta' },
      { label: 'Fees', value: at.fees, kind: 'delta' },
      { label: 'Equity out', value: r.exit_equity, kind: 'total' },
    ], compact);

    const labels = ['Close'].concat(r.rows.map((x) => 'Yr ' + x.year));
    VDL.chart('lbo-debt', {
      type: 'bar',
      data: { labels, datasets: [
        { label: 'Senior term loan', data: [su.senior_debt].concat(r.rows.map((x) => x.senior_end)), backgroundColor: COL.s1, borderColor: COL.surface, borderWidth: { top: 2 }, borderRadius: 2, maxBarThickness: 34 },
        { label: 'Subordinated notes', data: [su.sub_debt].concat(r.rows.map((x) => x.sub_debt)), backgroundColor: COL.s2, borderColor: COL.surface, borderWidth: { top: 2 }, borderRadius: 2, maxBarThickness: 34 },
      ].concat(r.liquidity_shortfall ? [{ label: 'Revolver', data: [0].concat(r.rows.map((x) => x.revolver)), backgroundColor: COL.s3, borderColor: COL.surface, borderWidth: { top: 2 }, borderRadius: 2, maxBarThickness: 34 }] : []) },
      options: {
        maintainAspectRatio: false,
        scales: { x: VDL.axis({ stacked: true, grid: { display: false }, ticks: { color: COL.ink2, font: { size: 10 } } }), y: VDL.axis({ stacked: true, ticks: { color: COL.muted, callback: (v) => F.crPlain(v) } }) },
        plugins: { tooltip: { mode: 'index', intersect: false, callbacks: { label: (ctx) => `${ctx.dataset.label}: ${F.cr(ctx.parsed.y)}` } } },
      },
    });
  }

  function build(host, m) {
    const c = m.c;
    if (!m.lbo) {
      host.innerHTML = `<div class="card"><h2 class="card-title">LBO not available</h2><p class="card-desc" style="margin:0">${VDL.esc(c.lbo.note || 'The default structure is not feasible for this company.')}</p></div>`;
      return;
    }
    syncEntry(m);
    const a = m.lbo;
    host.innerHTML = `
      <p class="section-intro">
        Could a financial sponsor take <strong>${VDL.esc(c.name)}</strong> private and earn its target return? This is a screening exercise on the same operating forecast as the DCF,
        struck at ${VDL.esc(c.trailing.basis)} EBITDA of ${F.cr(a.ebitda_ltm)}. Leveraged take-privates of Indian large caps are rare, so read the output as a discipline check:
        <strong>what price can pure cash generation and leverage support</strong>, with no strategic synergies. The Football Field uses the same model to back out the price a sponsor could pay.
      </p>
      <div class="panel-grid">
        <div class="card">
          <h2 class="card-title">Deal structure</h2>
          <div id="lbo-controls"></div>
          <label class="check-row"><input type="checkbox" id="lbo-tie"> Exit at the entry multiple</label>
          <div id="lbo-exit" style="margin-top:14px"></div>
          <div class="btn-group" style="margin-top:14px"><button type="button" class="btn" id="lbo-reset">Reset structure</button></div>
        </div>
        <div class="stack" id="lbo-out"></div>
      </div>`;

    const refresh = () => paint(m);
    const ctl = $('lbo-controls');
    let exitSlider;
    VDL.slider(ctl, { label: 'Offer premium to market', min: 0, max: 0.60, step: 0.005, value: m.lboPremium, fmt: (v) => F.pct(v, 1),
      hint: `Offer ${F.px(c.price * (1 + m.lboPremium))} per share at the default premium.`, onInput: (v) => { m.lboPremium = v; syncEntry(m); if (m.lboTie) exitSlider.set(a.exit_multiple); refresh(); } });
    VDL.slider(ctl, { label: 'Senior term loan', min: 0, max: 6, step: 0.05, value: a.senior_x, fmt: (v) => F.x(v, 2) + ' EBITDA', onInput: (v) => { a.senior_x = v; refresh(); } });
    VDL.slider(ctl, { label: 'Subordinated notes', min: 0, max: 3, step: 0.05, value: a.sub_x, fmt: (v) => F.x(v, 2) + ' EBITDA', onInput: (v) => { a.sub_x = v; refresh(); } });
    VDL.slider(ctl, { label: 'Senior interest rate', min: 0.06, max: 0.16, step: 0.0005, value: a.senior_rate, fmt: (v) => F.pct(v, 2), hint: 'Default: G-sec yield + 3.0 points.', onInput: (v) => { a.senior_rate = v; refresh(); } });
    VDL.slider(ctl, { label: 'Subordinated interest rate', min: 0.08, max: 0.20, step: 0.0005, value: a.sub_rate, fmt: (v) => F.pct(v, 2), hint: 'Default: G-sec yield + 5.5 points.', onInput: (v) => { a.sub_rate = v; refresh(); } });
    VDL.slider(ctl, { label: 'Cash sweep of excess cash flow', min: 0, max: 1, step: 0.05, value: a.sweep_pct, fmt: (v) => F.pct(v, 0), onInput: (v) => { a.sweep_pct = v; refresh(); } });
    VDL.slider(ctl, { label: 'Holding period', min: 3, max: 7, step: 1, value: a.hold_years, fmt: (v) => `${v} years`, onInput: (v) => { a.hold_years = v; refresh(); } });
    const maxExit = Math.max(60, Math.ceil(a.exit_multiple * 1.6));
    exitSlider = VDL.slider($('lbo-exit'), { label: 'Exit EV / EBITDA', min: 2, max: maxExit, step: 0.1, value: a.exit_multiple, fmt: (v) => F.x(v), onInput: (v) => { a.exit_multiple = v; refresh(); } });
    const tie = $('lbo-tie');
    tie.checked = m.lboTie;
    exitSlider.disable(m.lboTie);
    tie.addEventListener('change', () => { m.lboTie = tie.checked; exitSlider.disable(tie.checked); syncEntry(m); exitSlider.set(a.exit_multiple); refresh(); });
    $('lbo-reset').addEventListener('click', () => {
      m.lbo = VDL.clone(c.lbo.assumptions); m.lboPremium = D.market.lbo_premium; m.lboTie = true;
      VDL.show();
    });
    paint(m);
  }

  VDL.tabs.lbo = { build };
})();
