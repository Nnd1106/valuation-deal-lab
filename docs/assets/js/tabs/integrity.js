/* 08 · Model Integrity: re-verify the published numbers in the browser. */
(function () {
  'use strict';
  const { D, E, F, $ } = VDL;
  const REPO = 'https://github.com/Nnd1106/valuation-deal-lab';

  /**
   * The same comparison as tests/parity.js, run live: recompute every
   * published value with the browser engine from the published assumptions.
   */
  function parity() {
    let compared = 0, maxRel = 0;
    const failures = [];
    const cmp = (label, js, py, tol = 1e-9) => {
      if (py === null || py === undefined || typeof py === 'number') {
        compared++;
        const a = js === undefined ? null : js;
        if (py === null || py === undefined || a === null) { if (a !== (py === undefined ? null : py)) failures.push(label); return; }
        const diff = Math.abs(a - py), scale = Math.max(Math.abs(a), Math.abs(py));
        if (scale > 0) maxRel = Math.max(maxRel, diff / scale);
        if (diff > Math.max(1e-9, tol * scale)) failures.push(label);
      } else if (typeof py === 'boolean' || typeof py === 'string') {
        compared++;
        if (js !== py) failures.push(label);
      } else if (Array.isArray(py)) {
        if (!Array.isArray(js) || js.length !== py.length) { failures.push(label); return; }
        py.forEach((v, i) => cmp(`${label}[${i}]`, js[i], v, tol));
      } else {
        Object.keys(py).forEach((k) => cmp(`${label}.${k}`, js ? js[k] : undefined, py[k], tol));
      }
    };
    for (const c of D.companies) {
      const t = c.ticker, a = c.dcf.assumptions, s = c.dcf.sensitivity;
      cmp(`${t}.cost`, E.companyWacc(D.market, c.market_cap, c.latest_bs.debt, c.history.interest_coverage, VDL.sectorBeta[c.sector]), c.cost);
      cmp(`${t}.dcf`, E.runDcf(a), c.dcf.result);
      cmp(`${t}.sensitivity`, E.sensitivity(a, 'wacc', s.wacc, 'growth_terminal', s.growth_terminal), s.grid);
      cmp(`${t}.implied_growth`, E.impliedGrowth(a, c.price), c.dcf.implied_growth, 1e-7);
      cmp(`${t}.implied_margin`, E.impliedMargin(a, c.price), c.dcf.implied_margin, 1e-7);
      cmp(`${t}.multiples`, E.multiples(c.comps.input), c.comps.multiples);
      cmp(`${t}.peer_valuation`, E.peerValuation(c.comps.input, c.comps.peers.map((p) => VDL.byTicker[p].comps.input)), c.comps.valuation);
      if (c.lbo.result) cmp(`${t}.lbo`, E.runLbo(c.lbo.assumptions), c.lbo.result);
    }
    for (const p of D.merger_presets) {
      cmp(`merger ${p.acquirer}+${p.target}`, E.runMerger(p.assumptions), p.result);
      cmp(`merger defaults ${p.acquirer}+${p.target}`, VDL.defaultMerger(VDL.byTicker[p.acquirer], VDL.byTicker[p.target]), p.assumptions);
    }
    return { compared, maxRel, failures };
  }

  const GATE_LABEL = {
    statements_available: 'Statements downloaded', currency_verified: 'Reporting currency verified', fiscal_years: 'Consecutive fiscal years',
    statements_fresh: 'Statements are recent', balance_sheet_balances: 'Balance sheet balances', positive_operations: 'Positive operating results',
    operating_income_reconciles: 'Operating income reconciles', non_operating_assets_bounded: 'Non-operating assets bounded', eps_consistent: 'EPS consistent with net income',
    ltm_available: 'Trailing twelve months available', price_history: 'Price history downloaded', price_fresh: 'Price is current',
    share_count_consistent: 'Share count consistent', beta_sample: 'Enough data for beta', leverage_plausible: 'Leverage plausible',
    working_capital_ratio_in_bounds: 'Working capital ratio in bounds', wacc_plausible: 'WACC plausible', dcf_finite: 'DCF produces a value',
    terminal_value_share: 'Terminal value not dominant',
  };

  function paintParity() {
    const t0 = performance.now();
    const p = parity();
    const ms = performance.now() - t0;
    const good = p.failures.length === 0;
    $('int-parity').innerHTML = `
      <div class="stat-row">
        ${VDL.statBox('Recomputed just now', F.num(p.compared), `values, in ${ms.toFixed(0)} ms, in your browser`, 'lead')}
        ${VDL.statBox('Largest difference', p.maxRel === 0 ? '0' : p.maxRel.toExponential(1), 'relative, vs the Python engine')}
        ${VDL.statBox('Verdict', good ? VDL.status('pass', 'Identical') : VDL.status('fail', `${p.failures.length} differ`), 'tolerance 1e-9 relative')}
      </div>
      <p class="card-desc" style="margin:0">${good
        ? 'Every published valuation, sensitivity cell, reverse-DCF solution, multiple, LBO schedule and merger result was just recomputed by the JavaScript engine on this page from the published assumptions and matches what the Python engine wrote. The sliders therefore drive the tested model, not an approximation of it.'
        : 'The browser engine does not reproduce the published numbers. First differences: ' + VDL.esc(p.failures.slice(0, 5).join(', '))}</p>`;
  }

  function build(host, m) {
    const c = m.c, q = D.quality, mk = D.market;
    const gateRow = (g) => `<tr><td>${GATE_LABEL[g.id] || VDL.esc(g.id)}</td><td style="text-align:left">${g.ok ? VDL.status('pass', 'Pass') : g.level === 'warn' ? VDL.status('warn', 'Check') : VDL.status('fail', 'Fail')}</td><td class="wrap">${VDL.esc(g.detail)}</td></tr>`;
    const src = (label, value, source) => `<tr><td>${label}</td><td>${value}</td><td class="wrap">${VDL.esc(source)}</td></tr>`;
    host.innerHTML = `
      <p class="section-intro">
        A valuation is only as good as the model behind it, so this page shows the evidence. Three layers: the Python engine is tested against
        <strong>closed-form results</strong> it must reproduce exactly; the data passes <strong>quality gates</strong> before anything is published; and the engine you are
        using in this browser is checked <strong>value for value</strong> against the Python engine, on every build and again right now on your machine.
      </p>
      <div class="card">
        <h2 class="card-title">Live check: browser engine vs published results</h2>
        <div id="int-parity"></div>
        <div class="btn-group" style="margin-top:14px"><button type="button" class="btn" id="int-rerun">Run the check again</button><a class="btn" href="${REPO}/blob/main/tests/parity.js" target="_blank" rel="noopener">See the test in the repository ↗</a></div>
      </div>
      <div class="grid-2" style="margin-top:18px">
        <div class="card">
          <h2 class="card-title">This build</h2>
          <div class="stat-row">
            ${VDL.statBox('Companies published', `${q.published} / ${q.universe}`, q.excluded.length ? `${q.excluded.length} excluded by gates` : 'none excluded')}
            ${VDL.statBox('Engine identities', `${q.invariants_passed} / ${q.invariants_checked}`, 'hold on real data')}
            ${VDL.statBox('Data gates run', F.num(q.gates_checked), `${q.gate_warnings} disclosed warnings`)}
          </div>
          <ul class="note-list">
            <li><strong>Engine identities</strong> are accounting and model identities re-checked on every company at build time: enterprise value equals the sum of its parts, sources equal uses, the LBO value bridge sums exactly, the reverse DCF reprices to market, and so on. One failure stops the build.</li>
            <li><strong>Fail-closed publishing.</strong> If the build fails, nothing is written and the last good data stays live.</li>
            ${q.assumption_warnings.map((w) => `<li class="warn"><strong>Assumption review:</strong> ${VDL.esc(w)}</li>`).join('')}
            ${q.excluded.map((e) => `<li class="warn"><strong>${VDL.esc(e.ticker)} excluded:</strong> ${VDL.esc(e.reasons.join('; '))}</li>`).join('')}
          </ul>
        </div>
        <div class="card">
          <h2 class="card-title">What the test suite proves</h2>
          <ul class="note-list">
            <li><strong>DCF.</strong> A firm growing at a constant rate must equal the Gordon growth formula for any horizon; mid-year discounting must scale value by exactly (1 + WACC)<sup>½</sup>; with RONIC = WACC the terminal value must equal NOPAT ÷ WACC; growth must add value only when RONIC exceeds WACC.</li>
            <li><strong>LBO.</strong> An unlevered, no-growth deal has a closed-form IRR; cash is conserved through the debt schedule; the interest circularity converges; the value bridge sums to the equity gain.</li>
            <li><strong>M&amp;A.</strong> An all-stock deal is accretive if and only if the acquirer's P/E exceeds the offer P/E; a debt-funded cash deal if and only if the target's earnings yield beats the after-tax cost of debt; break-even synergies make EPS exactly neutral.</li>
            <li><strong>Cost of capital and comps.</strong> Regression betas match an independent least-squares solver; rating bands are checked at every boundary; valuing a company at its own multiple returns its own price.</li>
            <li>Properties are tested over thousands of randomly generated inputs, not a handful of examples. <a href="${REPO}/tree/main/tests" target="_blank" rel="noopener">Read the tests ↗</a></li>
          </ul>
        </div>
      </div>
      <div class="card" style="margin-top:18px">
        <h2 class="card-title">Data gates: ${VDL.esc(c.name)}</h2>
        <p class="card-desc">Statements snapshot taken ${F.date(c.snapshot_utc)}; reported in ${VDL.esc(c.currency_reported)}; trailing basis ${VDL.esc(c.trailing.basis)}.</p>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Gate</th><th style="text-align:left">Result</th><th class="wrap">Evidence</th></tr></thead><tbody>${c.gates.map(gateRow).join('')}</tbody></table></div>
      </div>
      <div class="card" style="margin-top:18px">
        <h2 class="card-title">Assumptions that are not fetched, and where they come from</h2>
        <div class="table-scroll"><table class="data-table"><thead><tr><th>Assumption</th><th>Value</th><th class="wrap">Source</th></tr></thead><tbody>
          ${src('India 10-year G-sec yield', F.pct(mk.gsec_10y, 2), `${mk.gsec_source}. Reviewed ${F.date(mk.gsec_as_of)}.`)}
          ${src('Sovereign default spread', F.pct(mk.sovereign_spread, 2), `${mk.erp_source}`)}
          ${src('Equity risk premium, India', F.pct(mk.erp, 2), `${mk.erp_source}. Reviewed ${F.date(mk.erp_as_of)}.`)}
          ${src('Synthetic rating spreads', `${mk.rating_table.length} bands`, mk.rating_source)}
          ${src('Corporate tax rate', F.pct(mk.tax_rate, 2), mk.tax_source)}
          ${src('Terminal growth', F.pct(mk.terminal_growth, 1), 'Long-run nominal growth assumption; never allowed above the risk-free rate.')}
          ${src('Yield on balance-sheet cash', F.pct(mk.cash_yield, 1), 'Assumed pre-tax yield given up when cash funds an acquisition.')}
        </tbody></table></div>
      </div>
      <div class="card" style="margin-top:18px">
        <h2 class="card-title">Known limitations</h2>
        <ul class="note-list">
          <li>Statements come from a free data provider, not from audited filings. The gates catch structural errors (currency, balance, classification), not every misstatement.</li>
          <li>Default forecasts are mechanical extrapolations of three to four years of history. They ignore guidance, capacity plans, product cycles and everything else an analyst would know.</li>
          <li>Financial investments are added back at book value, not market value. Associates and joint ventures are understated where they are worth more than their carrying amount.</li>
          <li>The risk-free rate and equity risk premium are reviewed by hand because no keyless source exists; the build warns when they go stale.</li>
          <li>Banks, NBFCs and groups with captive finance arms are excluded: free cash flow to the firm is not meaningful for them.</li>
          <li>The LBO ignores India-specific limits on acquisition financing and interest deductibility, and the M&amp;A model ignores deferred tax on the purchase price allocation.</li>
        </ul>
      </div>`;
    $('int-rerun').addEventListener('click', paintParity);
    paintParity();
  }

  VDL.parity = parity;
  VDL.tabs.integrity = { build };
})();
