/* 06 · M&A: accretion / dilution for any acquirer and target in the universe. */
(function () {
  'use strict';
  const { D, E, F, COL, $ } = VDL;
  const deal = { acq: null, tgt: null, a: null, synergyPct: null };

  const side = (c) => ({
    price: c.price, shares: c.shares, net_income: c.trailing.net_income, book_equity: c.latest_bs.equity,
    revenue: c.trailing.revenue, pretax_cost_debt: c.cost.pretax_cost_debt,
  });

  /** Mirror of engine/defaults.py default_merger (checked against the published presets on the integrity tab). */
  function defaultMerger(acq, tgt) {
    const mk = D.market, a = side(acq), t = side(tgt);
    return {
      acq_price: a.price, acq_shares: a.shares, acq_net_income: a.net_income,
      tgt_price: t.price, tgt_shares: t.shares, tgt_net_income: t.net_income, tgt_book_equity: t.book_equity,
      premium: mk.ma_premium, pct_cash: 0.5, cash_from_balance_sheet_pct: 0.5,
      cost_of_debt: a.pretax_cost_debt, yield_on_cash: mk.cash_yield, tax_rate: mk.tax_rate,
      synergies_pretax: mk.ma_synergy_pct_revenue * t.revenue, synergy_phase: 1.0,
      fee_pct: mk.ma_fee_pct, intangibles_pct: mk.ma_intangibles_pct, amort_years: mk.ma_amort_years,
    };
  }
  VDL.defaultMerger = defaultMerger;

  function setDeal(acqTicker, tgtTicker) {
    deal.acq = acqTicker; deal.tgt = tgtTicker;
    deal.a = defaultMerger(VDL.byTicker[acqTicker], VDL.byTicker[tgtTicker]);
    deal.synergyPct = D.market.ma_synergy_pct_revenue;
  }

  function pickDefault(c) {
    const preset = D.merger_presets.find((p) => p.acquirer === c.ticker) || D.merger_presets.find((p) => p.target === c.ticker);
    if (preset) return [preset.acquirer, preset.target];
    const peers = D.companies.filter((p) => p.sector === c.sector && p.ticker !== c.ticker).sort((x, y) => x.market_cap - y.market_cap);
    return [c.ticker, peers[0].ticker];
  }

  function grid(a) {
    const premiums = [0, 0.125, 0.25, 0.375, 0.5];
    const cash = [0, 0.25, 0.5, 0.75, 1];
    const g = E.accretionGrid(a, 'premium', premiums, 'pct_cash', cash);
    const body = g.map((row, i) => `<tr><th scope="row">${F.pct(cash[i], 0)} cash</th>${row.map((v, j) => {
      const t = Math.max(-1, Math.min(1, v / 0.10));
      return `<td style="background:${VDL.divergingBg(t)}" title="${F.pct(premiums[j], 1)} premium, ${F.pct(cash[i], 0)} cash: ${F.spct(v)} EPS">${F.spct(v)}</td>`;
    }).join('')}</tr>`).join('');
    return `<div class="axis-caption">Columns: offer premium · Rows: share of consideration paid in cash · Cells: change in acquirer EPS</div>
      <table class="heat"><thead><tr><th></th>${premiums.map((p) => `<th scope="col">${F.pct(p, 1)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table>
      <div class="legend-row" style="margin-top:10px"><span><span class="swatch" style="background:${VDL.divergingBg(0.8)}"></span>Accretive</span><span><span class="swatch" style="background:${VDL.divergingBg(0)}"></span>Neutral</span><span><span class="swatch" style="background:${VDL.divergingBg(-0.8)}"></span>Dilutive</span></div>
      <div class="legend-note">Full colour is reached at ±10% EPS. Other terms held at the current settings.</div>`;
  }

  function paint() {
    const a = deal.a;
    const acq = VDL.byTicker[deal.acq], tgt = VDL.byTicker[deal.tgt];
    const r = E.runMerger(a);
    const cashOnHand = acq.latest_bs.cash + acq.latest_bs.lt_investments;
    const combinedEbitda = acq.trailing.ebitda + tgt.trailing.ebitda;
    const verdict = r.accretion >= 0 ? 'accretive' : 'dilutive';
    const peRule = r.offer_pe !== null && r.acquirer_pe !== null
      ? `The acquirer trades on ${F.x(r.acquirer_pe)} earnings and is paying ${F.x(r.offer_pe)} for the target's. Shares issued at a lower multiple than the one being bought dilute EPS; shares issued at a higher multiple add to it. Here the stock portion ${r.acquirer_pe > r.offer_pe ? 'helps' : 'hurts'}.`
      : '';
    const contrib = (label, x, y) => `<tr><td>${label}</td><td>${F.crPlain(x)}</td><td>${F.crPlain(y)}</td><td>${F.pct(x / (x + y), 0)}</td><td>${F.pct(y / (x + y), 0)}</td></tr>`;

    $('ma-out').innerHTML = `
      <div class="card">
        <h2 class="card-title">${VDL.esc(acq.name)} acquires ${VDL.esc(tgt.name)}</h2>
        <div class="stat-row">
          ${VDL.statBox('EPS impact, run-rate', `<span class="${VDL.deltaClass(r.accretion)}">${F.spct(r.accretion)}</span>`, verdict, 'lead')}
          ${VDL.statBox('Pro forma EPS', '₹' + F.num(r.pro_forma_eps, 2), `standalone ₹${F.num(r.standalone_eps, 2)}`)}
          ${VDL.statBox('Break-even synergies', r.breakeven_synergies_pretax > 0 ? F.cr(r.breakeven_synergies_pretax) : 'none needed', r.breakeven_synergies_pretax > 0 ? `${F.pct(r.breakeven_synergies_pretax / tgt.trailing.revenue)} of target revenue` : 'accretive without synergies')}
          ${VDL.statBox('Purchase price (equity)', F.cr(r.purchase_price), `${F.px(r.offer_price)} per share`)}
          ${VDL.statBox('Acquirer holders own', F.pct(r.acquirer_ownership, 1), `${F.num(r.new_shares, 2)} cr new shares`)}
        </div>
        <p class="card-desc">${peRule}</p>
        ${r.cash_used > cashOnHand ? `<p class="card-desc">${VDL.status('warn', 'Cash check')} The deal draws ${F.cr(r.cash_used)} from the balance sheet, more than the acquirer's ${F.cr(cashOnHand)} of cash and investments. Lower the balance-sheet share.</p>` : ''}
        <div class="grid-2">
          <div>
            <div class="axis-caption">From standalone to pro forma net income, INR crore</div>
            <div class="chart-wrap short"><canvas id="ma-bridge" role="img" aria-label="Bridge from acquirer net income to pro forma net income"></canvas></div>
          </div>
          <div>${grid(a)}</div>
        </div>
      </div>
      <div class="grid-2">
        <div class="card">
          <h2 class="card-title">Deal terms and financing</h2>
          <div class="table-scroll"><table class="data-table loose"><tbody>
            <tr><td>Offer price per share</td><td>${F.px(r.offer_price)} (${F.pct(a.premium, 1)} premium)</td></tr>
            <tr><td>Equity purchase price</td><td>${F.cr(r.purchase_price)}</td></tr>
            <tr class="sub"><td>paid in cash</td><td>${F.cr(r.cash_consideration)}</td></tr>
            <tr class="sub"><td>paid in acquirer shares</td><td>${F.cr(r.stock_consideration)}</td></tr>
            <tr><td>Exchange ratio</td><td>${r.exchange_ratio.toFixed(4)} acquirer shares per target share</td></tr>
            <tr><td>Transaction fees (${F.pct(a.fee_pct, 0)})</td><td>${F.cr(r.fees)}</td></tr>
            <tr><td>Funded from balance-sheet cash</td><td>${F.cr(r.cash_used)}</td></tr>
            <tr><td>Funded with new debt</td><td>${F.cr(r.new_debt)} (${F.x(r.new_debt / combinedEbitda, 2)} combined EBITDA)</td></tr>
            <tr><td>Target book equity</td><td>${F.cr(a.tgt_book_equity)}</td></tr>
            <tr><td>Identified intangibles (${F.pct(a.intangibles_pct, 0)} of the excess)</td><td>${F.cr(r.intangibles)}, amortised over ${a.amort_years} years</td></tr>
            <tr class="total"><td>Goodwill created</td><td>${F.cr(r.goodwill)}</td></tr>
          </tbody></table></div>
        </div>
        <div class="card">
          <h2 class="card-title">Contribution analysis</h2>
          <p class="card-desc">What each side brings against what its shareholders end up owning (${F.pct(r.acquirer_ownership, 0)} / ${F.pct(r.target_ownership, 0)}).</p>
          <div class="table-scroll"><table class="data-table loose"><thead><tr><th>INR crore</th><th>${VDL.esc(acq.ticker)}</th><th>${VDL.esc(tgt.ticker)}</th><th>Acquirer %</th><th>Target %</th></tr></thead><tbody>
            ${contrib('Revenue', acq.trailing.revenue, tgt.trailing.revenue)}
            ${contrib('EBITDA', acq.trailing.ebitda, tgt.trailing.ebitda)}
            ${contrib('Net income', acq.trailing.net_income, tgt.trailing.net_income)}
            ${contrib('Market cap', acq.market_cap, tgt.market_cap)}
          </tbody></table></div>
          <p class="legend-note">Trailing figures (${VDL.esc(acq.trailing.basis)}). Run-rate view: one-off fees are funded but kept out of EPS; deferred tax on the intangible write-up is ignored; both companies are taken on trailing earnings.</p>
        </div>
      </div>`;

    const compact = (v) => { const abs = Math.abs(v); return (v < 0 ? '−' : '') + (abs >= 1e5 ? (abs / 1e5).toFixed(2) + 'L' : abs >= 1e3 ? (abs / 1e3).toFixed(1) + 'k' : abs.toFixed(0)); };
    VDL.waterfallChart('ma-bridge', [
      { label: 'Acquirer', value: a.acq_net_income, kind: 'total' },
      { label: 'Target', value: a.tgt_net_income, kind: 'delta' },
      { label: 'Synergies', value: r.synergies_after_tax, kind: 'delta' },
      { label: 'New debt', value: -r.debt_interest_after_tax, kind: 'delta' },
      { label: 'Lost yield', value: -r.foregone_interest_after_tax, kind: 'delta' },
      { label: 'Amortisation', value: -r.amortisation_after_tax, kind: 'delta' },
      { label: 'Pro forma', value: r.pro_forma_net_income, kind: 'total' },
    ], compact);
  }

  function build(host, m) {
    if (!deal.a || (deal.acq !== m.c.ticker && deal.tgt !== m.c.ticker)) setDeal(...pickDefault(m.c));
    const options = (sel) => D.sectors.map((s) => `<optgroup label="${VDL.esc(s.name)}">${s.tickers.map((t) =>
      `<option value="${VDL.esc(t)}" ${t === sel ? 'selected' : ''}>${VDL.esc(VDL.byTicker[t].name)}</option>`).join('')}</optgroup>`).join('');
    host.innerHTML = `
      <p class="section-intro">
        Does a deal add to or take away from the acquirer's earnings per share? Pick any two companies in the universe and set the terms.
        The pairs offered below are <strong>illustrations of the mechanics only</strong> and do not suggest that any transaction is planned or likely.
        Accretion is a financing outcome, not a measure of value created: a deal can be accretive and still destroy value if the price exceeds what the target is worth.
      </p>
      <div class="panel-grid">
        <div class="card">
          <h2 class="card-title">The deal</h2>
          <div class="control-group"><div class="control-label"><span>Acquirer</span></div><select class="plain" id="ma-acq" aria-label="Acquirer">${options(deal.acq)}</select></div>
          <div class="control-group"><div class="control-label"><span>Target</span></div><select class="plain" id="ma-tgt" aria-label="Target">${options(deal.tgt)}</select></div>
          <div class="control-group"><div class="control-label"><span>Illustrative pairs</span></div>
            <div class="btn-group">${D.merger_presets.map((p, i) => `<button type="button" class="btn" data-preset="${i}">${VDL.esc(p.acquirer)} + ${VDL.esc(p.target)}</button>`).join('')}</div></div>
          <div id="ma-controls"></div>
        </div>
        <div class="stack" id="ma-out"></div>
      </div>`;

    const a = deal.a;
    const tgt = VDL.byTicker[deal.tgt];
    const ctl = $('ma-controls');
    VDL.slider(ctl, { label: 'Offer premium', min: 0, max: 0.60, step: 0.005, value: a.premium, fmt: (v) => F.pct(v, 1), onInput: (v) => { a.premium = v; paint(); } });
    VDL.slider(ctl, { label: 'Paid in cash (rest in shares)', min: 0, max: 1, step: 0.05, value: a.pct_cash, fmt: (v) => F.pct(v, 0), onInput: (v) => { a.pct_cash = v; paint(); } });
    VDL.slider(ctl, { label: 'Cash funded from the balance sheet', min: 0, max: 1, step: 0.05, value: a.cash_from_balance_sheet_pct, fmt: (v) => F.pct(v, 0),
      hint: `The rest is new debt. Cash used gives up a ${F.pct(a.yield_on_cash, 1)} pre-tax yield.`, onInput: (v) => { a.cash_from_balance_sheet_pct = v; paint(); } });
    VDL.slider(ctl, { label: 'Pre-tax synergies, % of target revenue', min: 0, max: 0.10, step: 0.0025, value: deal.synergyPct, fmt: (v) => `${F.pct(v, 2)} · ${F.cr(v * tgt.trailing.revenue)}`,
      onInput: (v) => { deal.synergyPct = v; a.synergies_pretax = v * tgt.trailing.revenue; paint(); } });
    VDL.slider(ctl, { label: 'Cost of new debt', min: 0.05, max: 0.14, step: 0.0005, value: a.cost_of_debt, fmt: (v) => F.pct(v, 2), hint: `Default: the acquirer's pre-tax cost of debt.`, onInput: (v) => { a.cost_of_debt = v; paint(); } });
    VDL.slider(ctl, { label: 'Excess price allocated to intangibles', min: 0, max: 0.60, step: 0.05, value: a.intangibles_pct, fmt: (v) => F.pct(v, 0), onInput: (v) => { a.intangibles_pct = v; paint(); } });

    const change = () => {
      const x = $('ma-acq').value, y = $('ma-tgt').value;
      if (x === y) { $('ma-out').innerHTML = `<div class="card"><h2 class="card-title">Pick two different companies</h2><p class="card-desc" style="margin:0">The acquirer and the target are the same company.</p></div>`; return; }
      setDeal(x, y);
      build(host, m);
    };
    $('ma-acq').addEventListener('change', change);
    $('ma-tgt').addEventListener('change', change);
    host.querySelectorAll('[data-preset]').forEach((b) => b.addEventListener('click', () => {
      const p = D.merger_presets[Number(b.dataset.preset)];
      setDeal(p.acquirer, p.target);
      build(host, m);
    }));
    paint();
  }

  VDL.tabs.merger = { build };
})();
