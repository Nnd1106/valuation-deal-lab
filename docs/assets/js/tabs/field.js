/* 07 · Football Field: every method on one price axis. */
(function () {
  'use strict';
  const { D, E, F, COL, $ } = VDL;
  const SHARED = ['n_years', 'growth_start', 'growth_terminal', 'high_growth_years', 'margin_target',
    'margin_converge_years', 'tax_rate', 'da_pct', 'capex_pct', 'capex_pct_terminal', 'nwc_pct'];

  /** Rows of {label, family, low, mid, high, basis}; all in rupees per share, live assumptions. */
  function ranges(m) {
    const c = m.c, a = m.a, out = [];
    out.push({ label: '52-week trading range', family: 'market', low: c.lo52, mid: c.price, high: c.hi52, basis: 'traded closes over the last year' });

    const r = VDL.dcf(m);
    if (r) {
      const steps = [-0.005, 0, 0.005];
      const grid = E.sensitivity(a, 'wacc', steps.map((s) => a.wacc + s), 'growth_terminal', steps.map((s) => Math.max(0, a.growth_terminal + s)));
      const vals = grid.flat().filter((v) => v !== null && v > 0);
      if (vals.length) out.push({ label: 'DCF', family: 'dcf', low: Math.min(...vals), mid: r.per_share, high: Math.max(...vals), basis: `WACC ${F.pct(a.wacc, 2)} ± 0.5 pt, terminal growth ${F.pct(a.growth_terminal, 1)} ± 0.5 pt` });
    }

    const v = c.comps.valuation;
    [['ev_ebitda', 'Comps: EV / EBITDA'], ['ev_ebit', 'Comps: EV / EBIT'], ['pe', 'Comps: P / E']].forEach(([k, label]) => {
      const x = v[k];
      if (x && x.implied_low !== null && x.implied_high !== null && x.implied_high > 0) {
        out.push({ label, family: 'comps', low: Math.max(0, x.implied_low), mid: x.implied_mid, high: x.implied_high,
          basis: `peer ${F.x(x.stats.q1)} to ${F.x(x.stats.q3)} (first to third quartile, ${x.stats.n} peers)` });
      }
    });

    if (m.lbo && c.comps.multiples.ev_ebitda) {
      const band = Object.assign({}, m.lbo);
      for (const k of SHARED) band[k] = a[k];
      band.exit_multiple = c.comps.multiples.ev_ebitda;
      const bridge = VDL.netDebtBridge(c);
      const at = (irr) => { const ev = E.entryEvForIrr(band, irr); return ev === null ? null : (ev - bridge) / c.shares; };
      const lo = at(0.25), hi = at(0.15);
      if (lo !== null && hi !== null && hi > 0) {
        out.push({ label: 'LBO: sponsor price', family: 'lbo', low: Math.max(0, lo), mid: at(0.20), high: hi,
          basis: `price at which a sponsor earns 25% to 15% IRR, exiting at today's ${F.x(band.exit_multiple)} EV/EBITDA` });
      }
    }
    return out;
  }

  function build(host, m) {
    const c = m.c;
    const rows = ranges(m);
    const price = c.price;
    const colour = { market: COL.neutral, dcf: COL.s1, comps: COL.s2, lbo: COL.s3 };
    const methods = rows.filter((x) => x.family !== 'market');
    const below = methods.filter((x) => x.high < price).length;
    const above = methods.filter((x) => x.low > price).length;
    const within = methods.length - below - above;

    host.innerHTML = `
      <p class="section-intro">
        The classic banker's summary for <strong>${VDL.esc(c.name)}</strong>: each method contributes a value range per share, and the dashed line is the market price of ${F.px(price)}.
        Of ${methods.length} ranges, <strong>${within}</strong> contain the price, <strong>${below}</strong> sit entirely below it and <strong>${above}</strong> entirely above.
        The methods disagree by design: comps show what the market pays for similar businesses today, the DCF shows what the cash flows support under conservative assumptions,
        and the LBO shows what leverage alone can pay. The chart updates with every slider on the other tabs.
      </p>
      <div class="card">
        <h2 class="card-title">Valuation ranges, ₹ per share</h2>
        <div class="legend-row">
          <span><span class="swatch" style="background:${colour.market}"></span>Market</span>
          <span><span class="swatch" style="background:${colour.dcf}"></span>Intrinsic (DCF)</span>
          <span><span class="swatch" style="background:${colour.comps}"></span>Trading comps</span>
          <span><span class="swatch" style="background:${colour.lbo}"></span>Leveraged buyout</span>
        </div>
        <div class="chart-wrap" style="height:${70 + rows.length * 52}px"><canvas id="ff-chart" role="img" aria-label="Football field chart of valuation ranges by method against the market price"></canvas></div>
      </div>
      <div class="card" style="margin-top:18px">
        <h2 class="card-title">The same ranges as a table</h2>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Method</th><th>Low</th><th>Mid</th><th>High</th><th>Mid vs price</th><th class="wrap">Basis</th></tr></thead><tbody>
          ${rows.map((x) => `<tr><td>${x.label}</td><td>${F.px(x.low)}</td><td>${F.px(x.mid)}</td><td>${F.px(x.high)}</td>
            <td class="${x.family === 'market' ? '' : VDL.deltaClass(x.mid / price - 1)}">${x.family === 'market' ? '–' : F.spct(x.mid / price - 1, 0)}</td><td class="wrap">${VDL.esc(x.basis)}</td></tr>`).join('')}
        </tbody></table></div>
      </div>`;

    const top = Math.max(price, ...rows.map((x) => x.high)) * 1.22;
    VDL.chart('ff-chart', {
      type: 'bar',
      data: {
        labels: rows.map((x) => x.label),
        datasets: [{ data: rows.map((x) => [x.low, x.high]), backgroundColor: rows.map((x) => colour[x.family]), borderRadius: 4, borderSkipped: false, barThickness: 22 }],
      },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, layout: { padding: { top: 18, right: 8 } },
        scales: {
          x: VDL.axis({ min: 0, suggestedMax: top, ticks: { color: COL.muted, callback: (v) => F.rupees(v) } }),
          y: VDL.axis({ grid: { display: false }, ticks: { color: COL.ink, font: { size: 11.5 } } }),
        },
        plugins: {
          valueLabels: { fmt: (d) => `${F.px(d[0])} – ${F.px(d[1])}` },
          refLine: { value: price, label: `Price ${F.px(price)}` },
          tooltip: { callbacks: { label: (ctx) => { const x = rows[ctx.dataIndex]; return [`Low ${F.px(x.low)} · Mid ${F.px(x.mid)} · High ${F.px(x.high)}`, x.basis]; } } },
        },
      },
    });
  }

  VDL.fieldRanges = ranges;
  VDL.tabs.field = { build };
})();
