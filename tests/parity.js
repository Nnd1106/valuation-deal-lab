/* ---------------------------------------------------------------------
 * parity.js: browser engine vs Python engine.
 *
 *     node tests/parity.js
 *
 * Recomputes every published number with docs/assets/js/engine.js from the
 * assumptions in docs/data/deal-lab-data.json and compares it with what the
 * Python pipeline wrote. Any relative difference above 1e-9 fails.
 * ------------------------------------------------------------------- */
'use strict';
const fs = require('fs');
const path = require('path');

const E = require(path.join(__dirname, '..', 'docs', 'assets', 'js', 'engine.js'));
const data = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'docs', 'data', 'deal-lab-data.json'), 'utf8'));

const REL = 1e-9;
let compared = 0;
const failures = [];

function same(a, b, tol) {
  if (a === null || a === undefined || b === null || b === undefined) return (a ?? null) === (b ?? null);
  return Math.abs(a - b) <= Math.max(1e-9, tol * Math.max(Math.abs(a), Math.abs(b)));
}

function compare(label, js, py, tol = REL) {
  if (py === null || py === undefined || typeof py === 'number') {
    compared++;
    if (!(typeof js === 'number' || js === null || js === undefined) || !same(js, py, tol)) {
      failures.push(`${label}: js=${js} python=${py}`);
    }
  } else if (typeof py === 'boolean' || typeof py === 'string') {
    compared++;
    if (js !== py) failures.push(`${label}: js=${js} python=${py}`);
  } else if (Array.isArray(py)) {
    if (!Array.isArray(js) || js.length !== py.length) { failures.push(`${label}: array shape differs`); return; }
    py.forEach((v, i) => compare(`${label}[${i}]`, js[i], v, tol));
  } else {
    for (const k of Object.keys(py)) compare(`${label}.${k}`, js ? js[k] : undefined, py[k], tol);
  }
}

const byTicker = Object.fromEntries(data.companies.map((c) => [c.ticker, c]));
const sectorBeta = Object.fromEntries(data.sectors.map((s) => [s.key, s.unlevered_beta]));

for (const c of data.companies) {
  const t = c.ticker;

  // cost of capital
  compare(`${t}.cost`, E.companyWacc(data.market, c.market_cap, c.latest_bs.debt, c.history.interest_coverage, sectorBeta[c.sector]), c.cost);

  // DCF, sensitivity and reverse DCF
  const a = c.dcf.assumptions;
  compare(`${t}.dcf.result`, E.runDcf(a), c.dcf.result);
  const s = c.dcf.sensitivity;
  compare(`${t}.dcf.sensitivity`, E.sensitivity(a, 'wacc', s.wacc, 'growth_terminal', s.growth_terminal), s.grid);
  compare(`${t}.dcf.implied_growth`, E.impliedGrowth(a, c.price), c.dcf.implied_growth, 1e-7);
  compare(`${t}.dcf.implied_margin`, E.impliedMargin(a, c.price), c.dcf.implied_margin, 1e-7);

  // comps
  compare(`${t}.comps.multiples`, E.multiples(c.comps.input), c.comps.multiples);
  const peers = c.comps.peers.map((p) => byTicker[p].comps.input);
  compare(`${t}.comps.valuation`, E.peerValuation(c.comps.input, peers), c.comps.valuation);

  // LBO
  if (c.lbo.result) {
    compare(`${t}.lbo.result`, E.runLbo(c.lbo.assumptions), c.lbo.result);
    if (c.lbo.sponsor_band) {
      const band = Object.assign({}, c.lbo.assumptions, { exit_multiple: c.lbo.sponsor_band.exit_multiple });
      const bs = c.latest_bs;
      for (const [target, py] of Object.entries(c.lbo.sponsor_band.per_share_at_irr)) {
        const ev = E.entryEvForIrr(band, Number(target));
        const js = ev === null ? null : (ev - bs.debt - bs.minority + bs.cash + bs.lt_investments) / c.shares;
        compare(`${t}.lbo.sponsor_band[${target}]`, js, py, 1e-7);
      }
    }
  }
}

for (const p of data.merger_presets) {
  compare(`merger ${p.acquirer}>${p.target}`, E.runMerger(p.assumptions), p.result);
}

if (failures.length) {
  console.error(`PARITY FAILED: ${failures.length} of ${compared} values differ`);
  failures.slice(0, 40).forEach((f) => console.error('  ' + f));
  process.exit(1);
}
console.log(`parity ok: ${compared} values identical across ${data.companies.length} companies (Python engine vs browser engine)`);
