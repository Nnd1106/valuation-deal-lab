/* ---------------------------------------------------------------------
 * app.js: company selector, tab routing and the summary strip.
 * ------------------------------------------------------------------- */
(function () {
  'use strict';
  const { D, E, F, $ } = VDL;
  const TABS = ['overview', 'capital', 'dcf', 'comps', 'lbo', 'merger', 'field', 'integrity'];
  const state = VDL.state = { ticker: D.companies[0].ticker, tab: 'overview' };

  function readHash() {
    const [ticker, tab] = decodeURIComponent(location.hash.replace(/^#/, '')).split('/');
    if (VDL.byTicker[ticker]) state.ticker = ticker;
    if (TABS.includes(tab)) state.tab = tab;
  }
  function writeHash() {
    history.replaceState(null, '', `#${encodeURIComponent(state.ticker)}/${state.tab}`);
  }

  VDL.current = () => VDL.model(state.ticker);

  /** Summary strip: always reflects the live assumptions, not the defaults. */
  VDL.renderKpis = function () {
    const m = VDL.current();
    const c = m.c;
    const r = VDL.dcf(m);
    const mult = c.comps.multiples;
    const value = r ? r.per_share : null;
    const upside = r ? value / c.price - 1 : null;
    let implied = null;
    try { implied = E.impliedGrowth(m.a, c.price); } catch (e) { implied = null; }
    const tiles = [
      ['Share price', F.px(c.price), F.date(c.price_date)],
      ['Market cap', F.cr(c.market_cap), `${F.num(c.shares, 1)} cr shares`],
      ['Enterprise value', F.cr(mult.enterprise_value), 'net of cash and investments'],
      ['DCF value / share', value !== null && value > 0 ? F.px(value) : 'n.m.',
        upside !== null ? `<span class="${VDL.deltaClass(upside)}">${VDL.arrow(upside)} ${F.spct(upside, 0)} vs price</span>` : 'model undefined'],
      ['Price implies', implied !== null ? F.pct(implied) : 'outside range', `growth for ${m.a.high_growth_years} yrs · hist ${F.pct(c.history.revenue_cagr)}`],
      ['WACC', F.pct(m.a.wacc, 2), `Ke ${F.pct(m.a.cost_equity, 2)}${m.waccManual ? ' · manual' : ''}`],
      ['EV / EBITDA', F.x(mult.ev_ebitda), c.trailing.basis],
      ['P / E', F.x(mult.pe), c.trailing.basis],
    ];
    $('kpi-strip').innerHTML = tiles.map(([l, v, s]) =>
      `<div class="kpi-tile"><div class="kpi-label">${l}</div><div class="kpi-value">${v}</div><div class="kpi-sub">${s}</div></div>`).join('');
  };

  VDL.show = function () {
    document.querySelectorAll('.tab-btn').forEach((b) => {
      const on = b.dataset.tab === state.tab;
      b.classList.toggle('active', on);
      b.setAttribute('aria-selected', on ? 'true' : 'false');
      b.tabIndex = on ? 0 : -1;
    });
    document.querySelectorAll('.tab-panel').forEach((p) => p.classList.toggle('active', p.id === 'panel-' + state.tab));
    VDL.renderKpis();
    VDL.tabs[state.tab].build($('panel-' + state.tab), VDL.current());
    writeHash();
  };

  VDL.go = function (tab, ticker) {
    if (ticker && VDL.byTicker[ticker]) { state.ticker = ticker; $('company-select').value = ticker; }
    if (TABS.includes(tab)) state.tab = tab;
    VDL.show();
    window.scrollTo({ top: 0 });
  };

  function init() {
    const select = $('company-select');
    select.innerHTML = D.sectors.map((s) =>
      `<optgroup label="${VDL.esc(s.name)}">` +
      s.tickers.map((t) => `<option value="${VDL.esc(t)}">${VDL.esc(VDL.byTicker[t].name)} (${VDL.esc(t)})</option>`).join('') +
      '</optgroup>').join('');
    readHash();
    select.value = state.ticker;
    select.addEventListener('change', () => { state.ticker = select.value; VDL.show(); });

    const nav = $('tab-nav');
    nav.addEventListener('click', (ev) => {
      const b = ev.target.closest('.tab-btn');
      if (b) { state.tab = b.dataset.tab; VDL.show(); }
    });
    nav.addEventListener('keydown', (ev) => {
      if (ev.key !== 'ArrowRight' && ev.key !== 'ArrowLeft') return;
      const i = TABS.indexOf(state.tab);
      state.tab = TABS[(i + (ev.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length];
      VDL.show();
      $('tab-' + state.tab).focus();
    });
    window.addEventListener('hashchange', () => { readHash(); select.value = state.ticker; VDL.show(); });

    $('as-of').textContent = F.date(D.meta.valuation_date);
    $('footer-note').innerHTML =
      `<strong>Valuation &amp; Deal Lab</strong> · built by Niranjan Desai. ` +
      `Fundamentals and prices: ${VDL.esc(D.meta.source)}. Valuation date ${F.date(D.meta.valuation_date)}; ` +
      `data file generated ${F.date(D.meta.generated_utc)}. Amounts in INR crore unless stated.<br>` +
      `Every figure is computed by an open, tested engine: the Python engine is checked against closed-form results, and the ` +
      `browser engine is checked value for value against the Python engine (see <a href="#" id="footer-integrity">Model Integrity</a>). ` +
      `Default assumptions are mechanical, rules-based starting points, not forecasts. ` +
      `<strong>This is an educational project, not investment advice or a recommendation to buy or sell any security.</strong>`;
    $('footer-integrity').addEventListener('click', (ev) => { ev.preventDefault(); VDL.go('integrity'); });

    $('open-memo').addEventListener('click', () => VDL.memo.open(VDL.current()));
    VDL.show();
    $('boot').classList.add('done');
  }

  if (!D || !E || !window.Chart) {
    $('boot-label').textContent = 'Could not load the data file or the chart library. Check your connection and reload.';
  } else {
    init();
  }
})();
