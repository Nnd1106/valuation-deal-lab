/* memo.js: print-ready one-page valuation memo for the selected company,
 * built from the live assumptions (whatever the sliders currently say). */
(function () {
  'use strict';
  const { D, E, F, $ } = VDL;

  function render(m) {
    const c = m.c, a = m.a;
    const r = VDL.dcf(m);
    const k = VDL.cost(m);
    const mult = c.comps.multiples, v = c.comps.valuation;
    const value = r ? r.per_share : null;
    const upside = value !== null ? value / c.price - 1 : null;
    let ig = null, im = null;
    try { ig = E.impliedGrowth(a, c.price); im = E.impliedMargin(a, c.price); } catch (e) { /* undefined model */ }
    const rows = VDL.fieldRanges(m);
    const top = Math.max(c.price, ...rows.map((x) => x.high)) * 1.05;
    const pos = (x) => (Math.max(0, x) / top) * 100;
    const peerMid = v.ev_ebitda ? v.ev_ebitda.implied_mid : null;
    const years = c.annual.slice(-3);
    const ltm = c.ltm;
    const fin = (label, fn, ltmVal) => `<tr><td>${label}</td>${years.map((y) => `<td>${fn(y)}</td>`).join('')}${ltm ? `<td>${ltmVal}</td>` : ''}</tr>`;
    const multRow = (label, key, dp = 1) => `<tr><td>${label}</td><td>${F.x(mult[key], dp)}</td><td>${v[key] ? F.x(v[key].stats.median, dp) : '–'}</td><td>${v[key] ? F.px(v[key].implied_mid) : '–'}</td></tr>`;

    $('memo-page').innerHTML = `
      <div class="memo-head">
        <div><div style="font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#4a5568">Valuation memo · ${VDL.esc(VDL.sectorName[c.sector])}</div>
          <h2>${VDL.esc(c.name)} <span style="font-weight:400;color:#4a5568">(${VDL.esc(c.ticker)})</span></h2></div>
        <div class="meta">Valuation date ${F.date(D.meta.valuation_date)}<br>Valuation &amp; Deal Lab · Niranjan Desai</div>
      </div>
      <div class="memo-kpis">
        <div class="memo-kpi"><div class="l">Share price</div><div class="v">${F.px(c.price)}</div><div class="s">Mkt cap ${F.cr(c.market_cap)}</div></div>
        <div class="memo-kpi"><div class="l">DCF value</div><div class="v">${value !== null && value > 0 ? F.px(value) : 'n.m.'}</div><div class="s">${F.spct(upside, 0)} vs price</div></div>
        <div class="memo-kpi"><div class="l">Peer EV/EBITDA value</div><div class="v">${F.px(peerMid)}</div><div class="s">${peerMid ? F.spct(peerMid / c.price - 1, 0) + ' vs price' : ''}</div></div>
        <div class="memo-kpi"><div class="l">WACC</div><div class="v">${F.pct(a.wacc, 2)}</div><div class="s">Ke ${F.pct(a.cost_equity, 2)} · beta ${k.levered_beta.toFixed(2)}</div></div>
      </div>

      <h3>What the price implies</h3>
      <p>On the assumptions below, the discounted cash flows support ${value !== null && value > 0 ? F.px(value) : 'no positive value'} per share against a market price of ${F.px(c.price)}.
        ${ig !== null ? `To justify the price on growth alone, revenue would have to grow ${F.pct(ig)} a year for the next ${a.high_growth_years} years (the last ${c.annual.length - 1} years: ${F.pct(c.history.revenue_cagr)}).` : 'No growth rate in the tested range justifies the price on its own.'}
        ${im !== null ? `On margin alone, the steady-state EBIT margin would have to reach ${F.pct(im)} (own average: ${F.pct(c.history.avg_ebit_margin)}).` : ''}
        The DCF is a conservative, rules-based baseline, so the gap measures the expectations built into the price.</p>

      <div class="memo-cols">
        <div>
          <h3>DCF assumptions</h3>
          <table><tbody>
            <tr><td>Revenue growth</td><td>${F.pct(a.growth_start)} for ${a.high_growth_years} yrs, fading to ${F.pct(a.growth_terminal)}</td></tr>
            <tr><td>EBIT margin</td><td>${F.pct(a.margin_start)} moving to ${F.pct(a.margin_target)}</td></tr>
            <tr><td>Capex / revenue</td><td>${F.pct(a.capex_pct)} fading to ${F.pct(a.capex_pct_terminal)}</td></tr>
            <tr><td>Tax rate</td><td>${F.pct(a.tax_rate, 2)}</td></tr>
            <tr><td>WACC / terminal RONIC</td><td>${F.pct(a.wacc, 2)} / ${r ? F.pct(r.ronic_used, 2) : '–'}</td></tr>
            <tr><td>Enterprise value</td><td>${r ? F.cr(r.enterprise_value) : '–'}</td></tr>
            <tr><td>Terminal value share</td><td>${r ? F.pct(r.terminal_share, 0) : '–'}</td></tr>
          </tbody></table>
          <h3>Trading multiples (${VDL.esc(c.trailing.basis)})</h3>
          <table><thead><tr><th></th><th>${VDL.esc(c.ticker)}</th><th>Peer median</th><th>Implied ₹</th></tr></thead><tbody>
            ${multRow('EV / EBITDA', 'ev_ebitda')}${multRow('EV / EBIT', 'ev_ebit')}${multRow('P / E', 'pe')}${multRow('P / B', 'pb')}
          </tbody></table>
        </div>
        <div>
          <h3>Valuation ranges (₹ per share; line = price)</h3>
          <table><tbody>
            ${rows.map((x) => `<tr><td style="width:36%">${x.label}</td><td style="width:34%;padding:0 6px"><div class="memo-range"><div class="bar" style="left:${pos(x.low)}%;width:${Math.max(0.8, pos(x.high) - pos(x.low))}%"></div><div class="px" style="left:${pos(c.price)}%"></div></div></td><td>${F.px(x.low)} – ${F.px(x.high)}</td></tr>`).join('')}
          </tbody></table>
          <h3>Financial summary (INR crore)</h3>
          <table><thead><tr><th></th>${years.map((y) => `<th>${F.fy(y.fy)}</th>`).join('')}${ltm ? '<th>LTM</th>' : ''}</tr></thead><tbody>
            ${fin('Revenue', (y) => F.crPlain(y.revenue), ltm ? F.crPlain(ltm.revenue) : '')}
            ${fin('EBITDA', (y) => F.crPlain(y.ebitda), ltm ? F.crPlain(ltm.ebitda) : '')}
            ${fin('EBITDA margin', (y) => F.pct(y.ebitda / y.revenue), ltm ? F.pct(ltm.ebitda / ltm.revenue) : '')}
            ${fin('Net income', (y) => F.crPlain(y.net_income), ltm ? F.crPlain(ltm.net_income) : '')}
            ${fin('Net debt (debt − cash)', (y) => F.crPlain(y.net_debt), F.crPlain(c.latest_bs.net_debt))}
          </tbody></table>
        </div>
      </div>
      <div class="fine">
        Method: ten-year unlevered DCF with a value-driver terminal value; enterprise value net of cash and financial investments; peers are the ${VDL.esc(VDL.sectorName[c.sector])} group.
        Data: ${VDL.esc(D.meta.source)}. Every figure is produced by an open engine that is tested against closed-form results and re-verified in the browser.
        Default assumptions are mechanical starting points, not forecasts. Educational project; not investment advice or a recommendation to buy or sell any security.
      </div>`;
  }

  function open(m) {
    render(m);
    $('memo-overlay').classList.add('open');
    $('memo-close').focus();
  }
  function close() { $('memo-overlay').classList.remove('open'); }

  $('memo-close').addEventListener('click', close);
  $('memo-print').addEventListener('click', () => window.print());
  $('memo-overlay').addEventListener('click', (ev) => { if (ev.target === $('memo-overlay')) close(); });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape') close(); });

  VDL.memo = { open, close };
})();
