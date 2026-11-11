/* 02 · Cost of Capital: a transparent WACC build with sourced inputs. */
(function () {
  'use strict';
  const { D, E, F, COL, $ } = VDL;

  function peers(c) {
    const tax = D.market.tax_rate;
    return D.companies.filter((p) => p.sector === c.sector).map((p) => {
      const de = p.latest_bs.debt / p.market_cap;
      return { p, de, unlevered: E.unleverBeta(p.beta.raw, de, tax) };
    });
  }

  function paint(m) {
    const c = m.c, mk = D.market;
    const k = VDL.cost(m);
    $('cap-stats').innerHTML =
      VDL.statBox('WACC', F.pct(k.wacc, 2), `${F.pct(k.weight_equity, 0)} equity · ${F.pct(k.weight_debt, 0)} debt`, 'lead') +
      VDL.statBox('Cost of equity', F.pct(k.cost_equity, 2), `beta ${k.levered_beta.toFixed(2)}`) +
      VDL.statBox('After-tax cost of debt', F.pct(k.after_tax_cost_debt, 2), `${k.rating} synthetic rating`) +
      VDL.statBox('Risk-free rate', F.pct(k.risk_free, 2), 'G-sec less sovereign spread');
    const row = (label, formula, value, cls = '') =>
      `<tr class="${cls}"><td>${label}</td><td class="wrap"><span class="formula">${formula}</span></td><td>${value}</td></tr>`;
    $('cap-build').innerHTML = `<table class="data-table"><thead><tr><th>Step</th><th class="wrap">How it is derived</th><th>Value</th></tr></thead><tbody>
      <tr class="group"><td colspan="3">Cost of equity (CAPM)</td></tr>
      ${row('India 10-year G-sec yield', VDL.esc(mk.gsec_source), F.pct(m.cap.gsec, 2))}
      ${row('less sovereign default spread', 'India is rated Baa3; rupee government debt is not default-free', '−' + F.pct(mk.sovereign_spread, 2), 'sub')}
      ${row('Risk-free rate', 'G-sec yield − sovereign default spread', F.pct(k.risk_free, 2))}
      ${row('Unlevered (asset) beta', `median of ${VDL.esc(VDL.sectorName[c.sector])} peers, each unlevered at its own D/E`, k.unlevered_beta.toFixed(3))}
      ${row('Debt / equity', `${F.cr(c.latest_bs.debt)} debt ÷ ${F.cr(c.market_cap)} market cap`, F.pct(k.debt_to_equity, 1), 'sub')}
      ${row('Levered beta', 'βu × (1 + (1 − tax) × D/E)', k.levered_beta.toFixed(3))}
      ${row('Equity risk premium', VDL.esc(mk.erp_source), F.pct(k.erp, 2))}
      ${row('Cost of equity', 'risk-free + levered beta × equity risk premium', F.pct(k.cost_equity, 2), 'total')}
      <tr class="group"><td colspan="3">Cost of debt (synthetic rating)</td></tr>
      ${row('Interest coverage', 'EBIT ÷ interest expense, last fiscal year', k.interest_coverage === null ? 'no interest' : F.x(k.interest_coverage))}
      ${row('Synthetic rating and spread', VDL.esc(mk.rating_source), `${k.rating} · ${F.pct(k.default_spread, 2)}`)}
      ${row('Pre-tax cost of debt', 'G-sec yield + company default spread', F.pct(k.pretax_cost_debt, 2))}
      ${row('After-tax cost of debt', `× (1 − ${F.pct(k.tax_rate, 2)} tax); ${VDL.esc(mk.tax_source)}`, F.pct(k.after_tax_cost_debt, 2), 'total')}
      <tr class="group"><td colspan="3">Weighted average</td></tr>
      ${row('Weights at market value', 'equity at market cap, debt at book incl. leases', `${F.pct(k.weight_equity, 1)} / ${F.pct(k.weight_debt, 1)}`)}
      ${row('WACC', 'E/V × cost of equity + D/V × after-tax cost of debt', F.pct(k.wacc, 2), 'total')}
    </tbody></table>`;
    return k;
  }

  function build(host, m) {
    const c = m.c, mk = D.market;
    const set = peers(c);
    host.innerHTML = `
      <p class="section-intro">
        The discount rate, built from sourced inputs with nothing hidden. Country risk is counted once: the equity risk premium already includes
        India's country premium, so the risk-free rate strips the sovereign default spread out of the G-sec yield. The beta is a
        <strong>bottom-up sector beta</strong> (the median of peers' unlevered betas, relevered at this company's own capital structure) because a single
        company's regression beta is too noisy to trust on its own. Moving any input here flows straight into the DCF.
      </p>
      <div class="panel-grid">
        <div class="card">
          <h2 class="card-title">Market inputs</h2>
          <div id="cap-controls"></div>
          <div class="btn-group" style="margin-top:14px"><button type="button" class="btn" id="cap-reset">Reset to sourced defaults</button></div>
          <p class="legend-note">G-sec yield as of ${F.date(mk.gsec_as_of)}; equity risk premium as of ${F.date(mk.erp_as_of)}. These two cannot be fetched without an API key, so they are fixed in the pipeline config with their source and the build warns when they go stale.</p>
        </div>
        <div class="stack">
          <div class="card">
            <h2 class="card-title">${VDL.esc(c.name)}: WACC build</h2>
            <div class="stat-row" id="cap-stats"></div>
            <div class="table-scroll" id="cap-build"></div>
          </div>
          <div class="grid-2">
            <div class="card">
              <h2 class="card-title">Peer betas (5 years, weekly, vs Nifty 50)</h2>
              <div class="chart-wrap short"><canvas id="cap-beta" role="img" aria-label="Raw regression beta of each ${VDL.esc(VDL.sectorName[c.sector])} peer"></canvas></div>
              <div class="legend-note">Raw OLS betas. ${VDL.esc(c.ticker)} is highlighted; the other bars are its peers.</div>
            </div>
            <div class="card">
              <h2 class="card-title">From regression to sector beta</h2>
              <div class="table-scroll"><table class="data-table"><thead><tr><th>Company</th><th>Raw β</th><th>Std err</th><th>R²</th><th>Weeks</th><th>D/E</th><th>Unlevered β</th></tr></thead><tbody>
                ${set.map((x) => `<tr class="${x.p.ticker === c.ticker ? 'focus' : ''}"><td>${VDL.esc(x.p.ticker)}</td><td>${x.p.beta.raw.toFixed(2)}</td><td>${x.p.beta.se.toFixed(2)}</td><td>${F.pct(x.p.beta.r2, 0)}</td><td>${x.p.beta.n}</td><td>${F.pct(x.de, 1)}</td><td>${x.unlevered.toFixed(3)}</td></tr>`).join('')}
                <tr class="total"><td>Sector median</td><td></td><td></td><td></td><td></td><td></td><td>${VDL.sectorBeta[c.sector].toFixed(3)}</td></tr>
              </tbody></table></div>
              <div class="legend-note">Window: ${VDL.esc(c.beta.window)}. A beta with a standard error of ${c.beta.se.toFixed(2)} has a 95% range of roughly ±${(2 * c.beta.se).toFixed(2)}, which is why the sector median is used.</div>
            </div>
          </div>
        </div>
      </div>`;

    const controls = $('cap-controls');
    const refresh = () => { paint(m); VDL.applyCost(m); VDL.renderKpis(); };
    const sliders = {
      gsec: VDL.slider(controls, { label: 'India 10-year G-sec yield', min: 0.05, max: 0.10, step: 0.0005, value: m.cap.gsec, fmt: (v) => F.pct(v, 2),
        hint: 'Drives both the risk-free rate and the cost of debt.', onInput: (v) => { m.cap.gsec = v; refresh(); } }),
      erp: VDL.slider(controls, { label: 'Equity risk premium (India)', min: 0.04, max: 0.10, step: 0.0005, value: m.cap.erp, fmt: (v) => F.pct(v, 2),
        hint: `Mature-market premium plus India's country risk premium.`, onInput: (v) => { m.cap.erp = v; refresh(); } }),
      beta: VDL.slider(controls, { label: 'Unlevered sector beta', min: 0.30, max: 1.60, step: 0.005, value: m.cap.beta_u, fmt: (v) => v.toFixed(3),
        hint: 'Default: median of the peer group.', onInput: (v) => { m.cap.beta_u = v; refresh(); } }),
    };
    $('cap-reset').addEventListener('click', () => {
      m.cap = { gsec: mk.gsec_10y, erp: mk.erp, beta_u: VDL.sectorBeta[c.sector] };
      sliders.gsec.set(m.cap.gsec); sliders.erp.set(m.cap.erp); sliders.beta.set(m.cap.beta_u);
      refresh();
    });
    paint(m);

    const sorted = set.slice().sort((a, b) => b.p.beta.raw - a.p.beta.raw);
    VDL.chart('cap-beta', {
      type: 'bar',
      data: {
        labels: sorted.map((x) => x.p.ticker),
        datasets: [{ data: sorted.map((x) => x.p.beta.raw), backgroundColor: sorted.map((x) => (x.p.ticker === c.ticker ? COL.s1 : COL.neutral)), borderRadius: 3, maxBarThickness: 22 }],
      },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, layout: { padding: { right: 40 } },
        scales: { x: VDL.axis({ beginAtZero: true }), y: VDL.axis({ grid: { display: false }, ticks: { color: COL.ink2, font: { size: 10.5 } } }) },
        plugins: {
          valueLabels: { fmt: (v) => v.toFixed(2) },
          tooltip: { callbacks: { label: (ctx) => { const x = sorted[ctx.dataIndex]; return [`Raw beta ${x.p.beta.raw.toFixed(2)} (±${(2 * x.p.beta.se).toFixed(2)})`, `Unlevered ${x.unlevered.toFixed(2)}`]; } } },
        },
      },
    });
  }

  VDL.tabs.capital = { build };
})();
