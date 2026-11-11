/* ---------------------------------------------------------------------
 * engine.js: the valuation engine in the browser.
 *
 * A line-for-line mirror of the Python package in /engine (fin, wacc, dcf,
 * comps, lbo, merger). Same inputs, same key names, same iteration counts.
 * tests/parity.js runs this file in Node against the numbers the Python
 * pipeline published and fails the build on any difference above 1e-9, so
 * what a slider shows is the same model that was tested, not a re-write.
 * ------------------------------------------------------------------- */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.VDLEngine = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function ValueError(message) {
    const e = new Error(message);
    e.name = 'ValueError';
    return e;
  }
  const isValueError = (e) => e && e.name === 'ValueError';

  /* ---------------- fin ---------------- */
  function npv(rate, cashflows, times) {
    if (rate <= -1) throw ValueError('rate must be greater than -100%');
    let total = 0;
    for (let i = 0; i < cashflows.length; i++) {
      const t = times ? times[i] : i;
      total += cashflows[i] / Math.pow(1 + rate, t);
    }
    return total;
  }

  function bisectRoot(fn, lo, hi, iterations = 200) {
    let fLo = fn(lo);
    const fHi = fn(hi);
    if (!(Number.isFinite(fLo) && Number.isFinite(fHi)) || fLo * fHi > 0) return null;
    if (fLo === 0) return lo;
    if (fHi === 0) return hi;
    for (let i = 0; i < iterations; i++) {
      const mid = 0.5 * (lo + hi);
      const fMid = fn(mid);
      if (fMid === 0 || (hi - lo) < 1e-14) return mid;
      if (fLo * fMid < 0) hi = mid;
      else { lo = mid; fLo = fMid; }
    }
    return 0.5 * (lo + hi);
  }

  function irr(cashflows, times, lo = -0.99, hi = 100.0) {
    return bisectRoot((r) => npv(r, cashflows, times), lo, hi);
  }

  /* ---------------- wacc ---------------- */
  const unleverBeta = (beta, de, tax) => beta / (1 + (1 - tax) * de);
  const releverBeta = (beta, de, tax) => beta * (1 + (1 - tax) * de);
  const costOfEquity = (rf, beta, erp) => rf + beta * erp;
  const blumeAdjust = (beta) => (2 / 3) * beta + 1 / 3;

  /** table rows: [lowerBound | null, rating, spread], highest coverage band first. */
  function syntheticRating(coverage, table) {
    if (coverage === null || coverage === undefined || coverage === Infinity) return [table[0][1], table[0][2]];
    for (const [lower, rating, spread] of table) {
      if (lower === null || coverage >= lower) return [rating, spread];
    }
    const last = table[table.length - 1];
    return [last[1], last[2]];
  }

  function wacc(equityValue, debtValue, costEquity, pretaxCostDebt, taxRate) {
    const total = equityValue + debtValue;
    if (equityValue <= 0 || debtValue < 0 || total <= 0) throw ValueError('equity must be positive and debt non-negative');
    const we = equityValue / total;
    const wd = debtValue / total;
    const afterTaxKd = pretaxCostDebt * (1 - taxRate);
    return { wacc: we * costEquity + wd * afterTaxKd, weight_equity: we, weight_debt: wd, after_tax_cost_debt: afterTaxKd };
  }

  function companyWacc(mkt, marketCap, debt, interestCoverage, unleveredBeta) {
    const tax = mkt.tax_rate;
    const riskFree = mkt.gsec_10y - mkt.sovereign_spread;
    const de = debt / marketCap;
    const beta = releverBeta(unleveredBeta, de, tax);
    const ke = costOfEquity(riskFree, beta, mkt.erp);
    const [rating, spread] = syntheticRating(interestCoverage, mkt.rating_table);
    const pretaxKd = mkt.gsec_10y + spread;
    const w = wacc(marketCap, debt, ke, pretaxKd, tax);
    return {
      risk_free: riskFree, erp: mkt.erp, unlevered_beta: unleveredBeta, debt_to_equity: de,
      levered_beta: beta, cost_equity: ke, interest_coverage: interestCoverage, rating,
      default_spread: spread, pretax_cost_debt: pretaxKd, after_tax_cost_debt: w.after_tax_cost_debt,
      weight_equity: w.weight_equity, weight_debt: w.weight_debt, tax_rate: tax, wacc: w.wacc,
    };
  }

  /* ---------------- dcf ---------------- */
  function fadePath(nYears, start, terminal, holdYears) {
    if (nYears < 1) throw ValueError('n_years must be at least 1');
    const h = Math.max(0, Math.min(Math.trunc(holdYears), nYears - 1));
    const path = [];
    for (let t = 1; t <= nYears; t++) {
      path.push(t <= h ? start : start + (terminal - start) * (t - h) / (nYears - h));
    }
    return path;
  }
  const growthPath = fadePath;
  const capexPath = fadePath;

  function marginPath(nYears, marginStart, marginTarget, convergeYears) {
    const k = Math.max(1, Math.trunc(convergeYears));
    const path = [];
    for (let t = 1; t <= nYears; t++) path.push(marginStart + (marginTarget - marginStart) * Math.min(t, k) / k);
    return path;
  }

  function projectFcff(baseRevenue, growth, ebitMargin, taxRate, daPct, capexPct, nwcPct) {
    if (!(growth.length === ebitMargin.length && growth.length === capexPct.length)) {
      throw ValueError('growth, margin and capex paths must have equal length');
    }
    const rows = [];
    let prev = baseRevenue;
    for (let i = 0; i < growth.length; i++) {
      const revenue = prev * (1 + growth[i]);
      const ebit = revenue * ebitMargin[i];
      const nopat = ebit * (1 - taxRate);
      const da = revenue * daPct;
      const capex = revenue * capexPct[i];
      const deltaNwc = nwcPct * (revenue - prev);
      rows.push({
        year: i + 1, growth: growth[i], revenue, ebit_margin: ebitMargin[i], ebit,
        ebitda: ebit + da, nopat, da, capex, delta_nwc: deltaNwc, fcff: nopat + da - capex - deltaNwc,
      });
      prev = revenue;
    }
    return rows;
  }

  function terminalValue(nopatFinal, growthTerminal, waccRate, ronic) {
    if (waccRate <= growthTerminal) throw ValueError('WACC must exceed terminal growth');
    if (ronic <= 0) throw ValueError('RONIC must be positive');
    if (growthTerminal < 0) throw ValueError('terminal growth must be non-negative');
    const nopatNext = nopatFinal * (1 + growthTerminal);
    const reinvestmentRate = growthTerminal / ronic;
    const fcffNext = nopatNext * (1 - reinvestmentRate);
    return { nopat_next: nopatNext, reinvestment_rate: reinvestmentRate, fcff_next: fcffNext, value: fcffNext / (waccRate - growthTerminal) };
  }

  function enterpriseValue(fcff, tv, waccRate, midYear = true) {
    const n = fcff.length;
    const shift = midYear ? 0.5 : 0.0;
    const factors = [];
    for (let t = 1; t <= n; t++) factors.push(Math.pow(1 + waccRate, -(t - shift)));
    const pvFlows = fcff.map((cf, i) => cf * factors[i]);
    let pvExplicit = 0;
    for (const v of pvFlows) pvExplicit += v;
    const pvTv = tv * Math.pow(1 + waccRate, -n) * (midYear ? Math.pow(1 + waccRate, 0.5) : 1.0);
    const ev = pvExplicit + pvTv;
    return { discount_factors: factors, pv_flows: pvFlows, pv_explicit: pvExplicit, pv_terminal: pvTv, enterprise_value: ev, terminal_share: ev !== 0 ? pvTv / ev : NaN };
  }

  function equityBridge(ev, cash, ltInvestments, debt, minority, shares) {
    if (shares <= 0) throw ValueError('shares must be positive');
    const equity = ev + cash + ltInvestments - debt - minority;
    return { equity_value: equity, per_share: equity / shares };
  }

  function rollForward(valuePerShare, costEquityRate, yearsElapsed, dividends) {
    let value = valuePerShare * Math.pow(1 + costEquityRate, yearsElapsed);
    for (const [tPaid, amount] of (dividends || [])) {
      if (tPaid >= 0 && tPaid <= yearsElapsed) value -= amount * Math.pow(1 + costEquityRate, yearsElapsed - tPaid);
    }
    return value;
  }

  function runDcf(a) {
    const n = Math.trunc(a.n_years);
    const w = a.wacc;
    const ronic = a.ronic_tied ? w : a.terminal_ronic;
    const growth = growthPath(n, a.growth_start, a.growth_terminal, a.high_growth_years);
    const margins = marginPath(n, a.margin_start, a.margin_target, a.margin_converge_years);
    const capex = capexPath(n, a.capex_pct, a.capex_pct_terminal, a.high_growth_years);
    const rows = projectFcff(a.base_revenue, growth, margins, a.tax_rate, a.da_pct, capex, a.nwc_pct);
    const final = rows[rows.length - 1];
    const tv = terminalValue(final.nopat, a.growth_terminal, w, ronic);
    const ev = enterpriseValue(rows.map((r) => r.fcff), tv.value, w, Boolean(a.mid_year));
    rows.forEach((r, i) => { r.discount_factor = ev.discount_factors[i]; r.pv_fcff = ev.pv_flows[i]; });
    const bridge = equityBridge(ev.enterprise_value, a.cash, a.lt_investments, a.debt, a.minority, a.shares);
    const perShare = rollForward(bridge.per_share, a.cost_equity, a.years_since_fye, a.dividends_since_fye);
    return {
      rows, terminal: tv, ronic_used: ronic, pv_explicit: ev.pv_explicit, pv_terminal: ev.pv_terminal,
      enterprise_value: ev.enterprise_value, terminal_share: ev.terminal_share,
      implied_exit_ev_ebitda: final.ebitda > 0 ? tv.value / final.ebitda : null,
      equity_value: bridge.equity_value, per_share_fye: bridge.per_share, per_share: perShare,
    };
  }

  function grid(run, pick, a, keyX, valuesX, keyY, valuesY) {
    return valuesY.map((vy) => valuesX.map((vx) => {
      const b = Object.assign({}, a, { [keyX]: vx, [keyY]: vy });
      try { return pick(run(b)); } catch (e) { if (isValueError(e)) return null; throw e; }
    }));
  }
  const sensitivity = (a, keyX, valuesX, keyY, valuesY) => grid(runDcf, (r) => r.per_share, a, keyX, valuesX, keyY, valuesY);

  function impliedGrowth(a, price, lo = -0.20, hi = 0.60) {
    return bisectRoot((g) => runDcf(Object.assign({}, a, { growth_start: g })).per_share - price, lo, hi);
  }
  function impliedMargin(a, price, lo = 0.0, hi = 0.80) {
    return bisectRoot((m) => runDcf(Object.assign({}, a, { margin_target: m })).per_share - price, lo, hi);
  }

  /* ---------------- comps ---------------- */
  const EV_MULTIPLES = { ev_ebitda: 'ebitda', ev_ebit: 'ebit', ev_sales: 'revenue' };
  const ALL_MULTIPLES = ['ev_ebitda', 'ev_ebit', 'ev_sales', 'pe', 'pb'];
  const ratio = (num, den) => (num === null || den === null || num === undefined || den === undefined || den <= 0 || num <= 0) ? null : num / den;

  function multiples(c) {
    const marketCap = c.price * c.shares;
    const ev = marketCap + c.debt + c.minority - c.cash - c.lt_investments;
    const bvps = c.shares > 0 ? c.book_equity / c.shares : null;
    return {
      market_cap: marketCap, enterprise_value: ev, ev_ebitda: ratio(ev, c.ebitda), ev_ebit: ratio(ev, c.ebit),
      ev_sales: ratio(ev, c.revenue), pe: ratio(c.price, c.eps), pb: ratio(c.price, bvps),
    };
  }

  function quantile(values, q) {
    const s = values.slice().sort((x, y) => x - y);
    if (!s.length) throw ValueError('quantile of empty sequence');
    const idx = q * (s.length - 1);
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    return lo === hi ? s[lo] : s[lo] + (s[hi] - s[lo]) * (idx - lo);
  }

  function summary(values) {
    const v = values.filter((x) => x !== null && x !== undefined);
    if (!v.length) return null;
    let total = 0;
    for (const x of v) total += x;
    return { n: v.length, min: Math.min(...v), q1: quantile(v, 0.25), median: quantile(v, 0.5), q3: quantile(v, 0.75), max: Math.max(...v), mean: total / v.length };
  }

  function impliedPerShare(target, multiple, value) {
    if (value === null || value === undefined) return null;
    if (multiple in EV_MULTIPLES) {
      const metric = target[EV_MULTIPLES[multiple]];
      if (metric === null || metric === undefined || metric <= 0) return null;
      return (value * metric - target.debt - target.minority + target.cash + target.lt_investments) / target.shares;
    }
    if (multiple === 'pe') return target.eps && target.eps > 0 ? value * target.eps : null;
    if (multiple === 'pb') { const bvps = target.book_equity / target.shares; return bvps > 0 ? value * bvps : null; }
    throw new Error('unknown multiple ' + multiple);
  }

  function peerValuation(target, peers) {
    const pm = peers.map(multiples);
    const out = {};
    for (const m of ALL_MULTIPLES) {
      const stats = summary(pm.map((x) => x[m]));
      out[m] = stats === null ? null : {
        stats, implied_low: impliedPerShare(target, m, stats.q1),
        implied_mid: impliedPerShare(target, m, stats.median), implied_high: impliedPerShare(target, m, stats.q3),
      };
    }
    return out;
  }

  /* ---------------- lbo ---------------- */
  function sourcesAndUses(entryEv, ebitdaLtm, feePct, seniorX, subX) {
    const fees = entryEv * feePct;
    const senior = seniorX * ebitdaLtm;
    const sub = subX * ebitdaLtm;
    const uses = entryEv + fees;
    const equity = uses - senior - sub;
    return {
      entry_ev: entryEv, fees, total_uses: uses, senior_debt: senior, sub_debt: sub, sponsor_equity: equity,
      total_sources: senior + sub + equity, entry_multiple: entryEv / ebitdaLtm,
      leverage_x: (senior + sub) / ebitdaLtm, equity_pct: equity / uses,
    };
  }

  function runLbo(a) {
    const hold = Math.trunc(a.hold_years);
    const n = Math.trunc(a.n_years);
    if (!(hold >= 1 && hold <= n)) throw ValueError('hold_years must be between 1 and n_years');
    if (a.ebitda_ltm <= 0) throw ValueError('LTM EBITDA must be positive');
    const su = sourcesAndUses(a.entry_ev, a.ebitda_ltm, a.fee_pct, a.senior_x, a.sub_x);
    if (su.sponsor_equity <= 0) throw ValueError('debt exceeds total uses: sponsor equity must be positive');

    const growth = growthPath(n, a.growth_start, a.growth_terminal, a.high_growth_years).slice(0, hold);
    const margins = marginPath(n, a.margin_start, a.margin_target, a.margin_converge_years).slice(0, hold);
    const capex = capexPath(n, a.capex_pct, a.capex_pct_terminal, a.high_growth_years).slice(0, hold);
    const ops = projectFcff(a.base_revenue, growth, margins, a.tax_rate, a.da_pct, capex, a.nwc_pct);

    const taxRate = a.tax_rate;
    const seniorInitial = su.senior_debt;
    const sub = su.sub_debt;
    let senior = seniorInitial;
    let cash = 0.0;
    let shortfall = false;
    const rows = [];

    for (const op of ops) {
      const seniorBeg = senior;
      const mandatory = Math.min(seniorBeg, a.senior_amort_pct * seniorInitial);
      let interest = a.senior_rate * seniorBeg + a.sub_rate * sub;
      const step = (i) => {
        const ebt = op.ebit - i;
        const tax = Math.max(ebt, 0.0) * taxRate;
        const netIncome = ebt - tax;
        const cfads = netIncome + op.da - op.capex - op.delta_nwc;
        const sweep = Math.min(seniorBeg - mandatory, Math.max(0.0, cfads - mandatory) * a.sweep_pct);
        return { ebt, tax, netIncome, cfads, sweep, seniorEnd: seniorBeg - mandatory - sweep };
      };
      for (let k = 0; k < 500; k++) {
        const s = step(interest);
        const base = a.interest_on_average ? 0.5 * (seniorBeg + s.seniorEnd) : seniorBeg;
        const next = a.senior_rate * base + a.sub_rate * sub;
        const converged = Math.abs(next - interest) <= 1e-13 * Math.max(1.0, Math.abs(interest));
        interest = next;
        if (converged) break;
      }
      const s = step(interest);
      senior = s.seniorEnd;
      cash = cash + s.cfads - mandatory - s.sweep;
      if (cash < -1e-9) shortfall = true;
      const totalDebt = senior + sub;
      rows.push({
        year: op.year, revenue: op.revenue, ebitda: op.ebitda, ebit: op.ebit, interest, ebt: s.ebt, tax: s.tax,
        net_income: s.netIncome, da: op.da, capex: op.capex, delta_nwc: op.delta_nwc, cfads: s.cfads,
        mandatory, sweep: s.sweep, senior_beg: seniorBeg, senior_end: senior, sub_debt: sub, cash_end: cash,
        total_debt: totalDebt, net_debt: totalDebt - cash,
        debt_to_ebitda: op.ebitda > 0 ? totalDebt / op.ebitda : null,
        interest_cover: interest > 0 ? op.ebitda / interest : null,
      });
    }

    const final = rows[rows.length - 1];
    const exitEv = a.exit_multiple * final.ebitda;
    const exitNetDebt = final.net_debt;
    const exitEquity = exitEv - exitNetDebt;
    const equityIn = su.sponsor_equity;
    const flows = [-equityIn];
    for (let i = 0; i < hold - 1; i++) flows.push(0.0);
    flows.push(exitEquity);
    const entryNetDebt = seniorInitial + sub;
    return {
      sources_uses: su, rows, exit_ev: exitEv, exit_net_debt: exitNetDebt, exit_equity: exitEquity,
      moic: exitEquity / equityIn, irr: exitEquity > 0 ? irr(flows) : null,
      value_creation: exitEquity - equityIn,
      attribution: {
        ebitda_growth: (final.ebitda - a.ebitda_ltm) * su.entry_multiple,
        multiple_expansion: (a.exit_multiple - su.entry_multiple) * final.ebitda,
        deleveraging: entryNetDebt - exitNetDebt,
        fees: -su.fees,
      },
      liquidity_shortfall: shortfall,
    };
  }

  function entryEvForIrr(a, targetIrr) {
    const floor = (a.senior_x + a.sub_x) * a.ebitda_ltm / (1.0 + a.fee_pct) + 0.25 * a.ebitda_ltm;
    const gap = (ev) => {
      let r;
      try { r = runLbo(Object.assign({}, a, { entry_ev: ev })).irr; } catch (e) { if (isValueError(e)) return NaN; throw e; }
      return (r !== null ? r : -1.0) - targetIrr;
    };
    return bisectRoot(gap, floor, 200.0 * a.ebitda_ltm);
  }
  const irrGrid = (a, keyX, valuesX, keyY, valuesY) => grid(runLbo, (r) => r.irr, a, keyX, valuesX, keyY, valuesY);

  /* ---------------- merger ---------------- */
  function runMerger(a) {
    if (!(a.pct_cash >= 0 && a.pct_cash <= 1)) throw ValueError('pct_cash must be between 0 and 1');
    if (a.acq_shares <= 0 || a.tgt_shares <= 0 || a.acq_price <= 0 || a.tgt_price <= 0) throw ValueError('prices and share counts must be positive');
    const tax = a.tax_rate;
    const offerPrice = a.tgt_price * (1 + a.premium);
    const purchasePrice = offerPrice * a.tgt_shares;
    const cashConsideration = purchasePrice * a.pct_cash;
    const stockConsideration = purchasePrice - cashConsideration;
    const newShares = stockConsideration / a.acq_price;
    const fees = purchasePrice * a.fee_pct;
    const cashNeeded = cashConsideration + fees;
    const cashUsed = cashNeeded * a.cash_from_balance_sheet_pct;
    const newDebt = cashNeeded - cashUsed;
    const excess = Math.max(0.0, purchasePrice - a.tgt_book_equity);
    const intangibles = excess * a.intangibles_pct;
    const amortisation = a.amort_years > 0 ? intangibles / a.amort_years : 0.0;
    const goodwill = purchasePrice - a.tgt_book_equity - intangibles;
    const synergiesAt = a.synergies_pretax * a.synergy_phase * (1 - tax);
    const debtInterestAt = newDebt * a.cost_of_debt * (1 - tax);
    const foregoneAt = cashUsed * a.yield_on_cash * (1 - tax);
    const amortAt = amortisation * (1 - tax);
    const standaloneEps = a.acq_net_income / a.acq_shares;
    const pfShares = a.acq_shares + newShares;
    const pfNiEx = a.acq_net_income + a.tgt_net_income - debtInterestAt - foregoneAt - amortAt;
    const pfNi = pfNiEx + synergiesAt;
    const pfEps = pfNi / pfShares;
    const realised = (1 - tax) * a.synergy_phase;
    const tgtEps = a.tgt_net_income / a.tgt_shares;
    return {
      offer_price: offerPrice, purchase_price: purchasePrice, cash_consideration: cashConsideration,
      stock_consideration: stockConsideration, new_shares: newShares, exchange_ratio: newShares / a.tgt_shares,
      fees, cash_used: cashUsed, new_debt: newDebt, intangibles, amortisation, goodwill,
      synergies_after_tax: synergiesAt, debt_interest_after_tax: debtInterestAt,
      foregone_interest_after_tax: foregoneAt, amortisation_after_tax: amortAt,
      standalone_eps: standaloneEps, pro_forma_net_income: pfNi, pro_forma_shares: pfShares, pro_forma_eps: pfEps,
      accretion: standaloneEps > 0 ? pfEps / standaloneEps - 1.0 : null,
      breakeven_synergies_pretax: realised > 0 ? (standaloneEps * pfShares - pfNiEx) / realised : null,
      acquirer_ownership: a.acq_shares / pfShares, target_ownership: newShares / pfShares,
      acquirer_pe: standaloneEps > 0 ? a.acq_price / standaloneEps : null,
      offer_pe: tgtEps > 0 ? offerPrice / tgtEps : null,
    };
  }
  const accretionGrid = (a, keyX, valuesX, keyY, valuesY) => grid(runMerger, (r) => r.accretion, a, keyX, valuesX, keyY, valuesY);

  return {
    VERSION: '1.0.0',
    npv, irr, bisectRoot,
    unleverBeta, releverBeta, costOfEquity, blumeAdjust, syntheticRating, wacc, companyWacc,
    fadePath, growthPath, capexPath, marginPath, projectFcff, terminalValue, enterpriseValue,
    equityBridge, rollForward, runDcf, sensitivity, impliedGrowth, impliedMargin,
    ALL_MULTIPLES, multiples, quantile, summary, impliedPerShare, peerValuation,
    sourcesAndUses, runLbo, entryEvForIrr, irrGrid, runMerger, accretionGrid,
  };
});
