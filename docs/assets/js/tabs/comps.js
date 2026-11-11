/* 04 · Comps: trading multiples against the peer group. */
(function () {
  'use strict';
  const { D, E, F, COL, $ } = VDL;
  const LABEL = { ev_ebitda: 'EV / EBITDA', ev_ebit: 'EV / EBIT', ev_sales: 'EV / Sales', pe: 'P / E', pb: 'P / B' };
  const view = { multiple: 'ev_ebitda', sort: 'market_cap', desc: true };

  function rowsFor(c) {
    return D.companies.filter((p) => p.sector === c.sector).map((p) => {
      const h = p.history, mult = p.comps.multiples, t = p.trailing;
      const roic = h.roic[h.roic.length - 1];
      return {
        ticker: p.ticker, name: p.name, market_cap: mult.market_cap, enterprise_value: mult.enterprise_value,
        ev_ebitda: mult.ev_ebitda, ev_ebit: mult.ev_ebit, ev_sales: mult.ev_sales, pe: mult.pe, pb: mult.pb,
        margin: t.ebitda / t.revenue, growth: h.revenue_growth[h.revenue_growth.length - 1], roic,
      };
    });
  }

  function table(c, rows) {
    const cols = [
      ['market_cap', 'Mkt cap', (v) => F.cr(v)], ['enterprise_value', 'EV', (v) => F.cr(v)],
      ['ev_ebitda', 'EV/EBITDA', (v) => F.x(v)], ['ev_ebit', 'EV/EBIT', (v) => F.x(v)], ['ev_sales', 'EV/Sales', (v) => F.x(v, 2)],
      ['pe', 'P/E', (v) => F.x(v)], ['pb', 'P/B', (v) => F.x(v)],
      ['margin', 'EBITDA mgn', (v) => F.pct(v)], ['growth', 'Rev growth', (v) => F.spct(v)], ['roic', 'ROIC', (v) => (v === null ? 'n.m.' : F.pct(v))],
    ];
    const sorted = rows.slice().sort((a, b) => {
      const x = a[view.sort], y = b[view.sort];
      if (x === null) return 1;
      if (y === null) return -1;
      return view.desc ? y - x : x - y;
    });
    const peers = rows.filter((r) => r.ticker !== c.ticker);
    const stat = (label, q) => `<tr class="${q === 0.5 ? 'total' : 'sub'}"><td>${label}</td><td></td><td></td>${['ev_ebitda', 'ev_ebit', 'ev_sales', 'pe', 'pb'].map((k) => {
      const v = peers.map((r) => r[k]).filter((x) => x !== null);
      return `<td>${v.length ? F.x(E.quantile(v, q), k === 'ev_sales' ? 2 : 1) : '–'}</td>`;
    }).join('')}${['margin', 'growth', 'roic'].map((k) => {
      const v = peers.map((r) => r[k]).filter((x) => x !== null);
      return `<td>${v.length ? F.pct(E.quantile(v, q)) : '–'}</td>`;
    }).join('')}</tr>`;
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Company</th>${cols.map(([k, l]) =>
      `<th class="sortable" data-sort="${k}" aria-sort="${view.sort === k ? (view.desc ? 'descending' : 'ascending') : 'none'}">${l}${view.sort === k ? (view.desc ? ' ▾' : ' ▴') : ''}</th>`).join('')}</tr></thead><tbody>
      ${sorted.map((r) => `<tr class="${r.ticker === c.ticker ? 'focus' : ''}"><td>${VDL.esc(r.name)}</td>${cols.map(([k, , f]) => `<td>${f(r[k])}</td>`).join('')}</tr>`).join('')}
      ${stat('Peer first quartile', 0.25)}${stat('Peer median', 0.5)}${stat('Peer third quartile', 0.75)}
    </tbody></table></div>`;
  }

  function implied(c) {
    const v = c.comps.valuation, own = c.comps.multiples;
    const body = E.ALL_MULTIPLES.map((k) => {
      const x = v[k];
      if (!x) return `<tr><td>${LABEL[k]}</td><td colspan="7">not meaningful for the peer group</td></tr>`;
      const dp = k === 'ev_sales' ? 2 : 1;
      const up = x.implied_mid === null ? null : x.implied_mid / c.price - 1;
      return `<tr><td>${LABEL[k]}</td><td>${F.x(own[k], dp)}</td><td>${F.x(x.stats.median, dp)}</td>
        <td>${F.px(x.implied_low)}</td><td><strong style="color:var(--text-primary)">${F.px(x.implied_mid)}</strong></td><td>${F.px(x.implied_high)}</td>
        <td class="${VDL.deltaClass(up)}">${F.spct(up, 0)}</td></tr>`;
    }).join('');
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>Multiple</th><th>Own</th><th>Peer median</th><th>At Q1</th><th>At median</th><th>At Q3</th><th>vs price</th></tr></thead><tbody>${body}</tbody></table></div>
      <div class="legend-note">"At Q1 / median / Q3": value per share at the peer group's first quartile, median and third quartile multiple.</div>`;
  }

  function chart(c, rows) {
    const k = view.multiple;
    const data = rows.filter((r) => r[k] !== null).sort((a, b) => b[k] - a[k]);
    const peerVals = data.filter((r) => r.ticker !== c.ticker).map((r) => r[k]);
    const med = peerVals.length ? E.quantile(peerVals, 0.5) : null;
    const dp = k === 'ev_sales' ? 2 : 1;
    VDL.chart('comps-chart', {
      type: 'bar',
      data: { labels: data.map((r) => r.ticker), datasets: [{ data: data.map((r) => r[k]), backgroundColor: data.map((r) => (r.ticker === c.ticker ? COL.s1 : COL.neutral)), borderRadius: 3, maxBarThickness: 24 }] },
      options: {
        indexAxis: 'y', maintainAspectRatio: false, layout: { padding: { right: 46, top: 16 } },
        scales: { x: VDL.axis({ beginAtZero: true, ticks: { color: COL.muted, callback: (v) => v + 'x' } }), y: VDL.axis({ grid: { display: false }, ticks: { color: COL.ink2, font: { size: 10.5 } } }) },
        plugins: {
          valueLabels: { fmt: (v) => F.x(v, dp) },
          refLine: { value: med, label: med === null ? '' : `Peer median ${F.x(med, dp)}` },
          tooltip: { callbacks: { title: (items) => data[items[0].dataIndex].name, label: (ctx) => `${LABEL[k]} ${F.x(ctx.parsed.x, dp)}` } },
        },
      },
    });
  }

  function build(host, m) {
    const c = m.c;
    const rows = rowsFor(c);
    host.innerHTML = `
      <p class="section-intro">
        How the market prices <strong>${VDL.esc(c.name)}</strong> against its ${VDL.esc(VDL.sectorName[c.sector])} peers on ${VDL.esc(c.trailing.basis)} figures.
        Enterprise value is built the same way as in the DCF: market cap plus debt and minorities, less cash, short-term and long-term financial investments.
        That keeps the numerator consistent with EBITDA and EBIT, which exclude the income those investments earn. The provider's own EV does not make this adjustment.
      </p>
      <div class="card">
        <h2 class="card-title">Peer group</h2>
        <div id="comps-table">${table(c, rows)}</div>
        <div class="legend-note">Click a column heading to sort. Quartiles and the median exclude ${VDL.esc(c.ticker)} itself. "n.m." marks a multiple with a non-positive denominator, or a return on negligible invested capital.</div>
      </div>
      <div class="grid-2" style="margin-top:18px">
        <div class="card">
          <h2 class="card-title">One multiple across the group</h2>
          <div class="btn-group" style="margin-bottom:12px" role="group" aria-label="Multiple">${E.ALL_MULTIPLES.map((k) => `<button type="button" class="btn ${k === view.multiple ? 'active' : ''}" data-mult="${k}">${LABEL[k]}</button>`).join('')}</div>
          <div class="chart-wrap"><canvas id="comps-chart" role="img" aria-label="Selected trading multiple for each peer"></canvas></div>
        </div>
        <div class="card">
          <h2 class="card-title">What peer multiples imply for ${VDL.esc(c.ticker)} (₹ per share)</h2>
          <p class="card-desc">Each peer multiple applied to this company's own trailing metric, then bridged to equity. Market price: ${F.px(c.price)}.</p>
          ${implied(c)}
        </div>
      </div>`;

    const rebind = () => {
      $('comps-table').querySelectorAll('[data-sort]').forEach((th) => th.addEventListener('click', () => {
        view.desc = view.sort === th.dataset.sort ? !view.desc : true;
        view.sort = th.dataset.sort;
        $('comps-table').innerHTML = table(c, rows);
        rebind();
      }));
    };
    rebind();
    host.querySelectorAll('[data-mult]').forEach((b) => b.addEventListener('click', () => {
      view.multiple = b.dataset.mult;
      host.querySelectorAll('[data-mult]').forEach((x) => x.classList.toggle('active', x === b));
      chart(c, rows);
    }));
    chart(c, rows);
  }

  VDL.tabs.comps = { build };
})();
