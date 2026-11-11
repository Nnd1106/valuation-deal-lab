/* ---------------------------------------------------------------------
 * ui.js: shared state, formatting, controls and chart helpers.
 * No valuation math lives here or in any tab: every number comes from
 * engine.js, the parity-tested mirror of the Python engine.
 * ------------------------------------------------------------------- */
(function () {
  'use strict';

  const D = window.VDL_DATA;
  const E = window.VDLEngine;
  const VDL = window.VDL = { D, E, tabs: {}, charts: {} };

  /* ---------------- Palette ---------------- */
  // Categorical slots validated against surface #0f131c (lightness band,
  // chroma, colour-vision separation, contrast). Status colours are reserved
  // for pass / warn / fail and always ship with an icon and a label.
  const COL = VDL.COL = {
    s1: '#3987e5', s2: '#d95926', s3: '#199e70', s4: '#c98500', s5: '#d55181',
    neg: '#e66767', neutral: '#6b7a8f', ink: '#e6edf7', ink2: '#9fb0c3', muted: '#6b7a8f',
    grid: 'rgba(255,255,255,0.06)', axis: 'rgba(255,255,255,0.16)', surface: '#0f131c',
    good: '#0ca30c', warning: '#fab219', critical: '#d03b3b',
  };
  const MONO = '"SFMono-Regular", Consolas, "Cascadia Mono", "Liberation Mono", monospace';

  /* ---------------- Lookups ---------------- */
  VDL.byTicker = Object.fromEntries(D.companies.map((c) => [c.ticker, c]));
  VDL.sectorName = Object.fromEntries(D.sectors.map((s) => [s.key, s.name]));
  VDL.sectorBeta = Object.fromEntries(D.sectors.map((s) => [s.key, s.unlevered_beta]));
  const clone = VDL.clone = (o) => JSON.parse(JSON.stringify(o));

  /* ---------------- Formatting ---------------- */
  const nf = (dp) => new Intl.NumberFormat('en-IN', { minimumFractionDigits: dp, maximumFractionDigits: dp });
  const NF = [nf(0), nf(1), nf(2), nf(3)];
  const ok = (x) => x !== null && x !== undefined && Number.isFinite(x);
  const F = VDL.F = {
    ok,
    num: (x, dp = 0) => (ok(x) ? NF[dp].format(x) : '–'),
    /** rupees per share */
    px: (x) => (ok(x) ? '₹' + NF[Math.abs(x) >= 1000 ? 0 : Math.abs(x) >= 100 ? 1 : 2].format(x) : '–'),
    /** INR crore, switching to lakh crore for very large amounts */
    cr: (x) => {
      if (!ok(x)) return '–';
      const sign = x < 0 ? '−' : '';
      const v = Math.abs(x);
      return v >= 1e5 ? `${sign}₹${NF[2].format(v / 1e5)} L cr` : `${sign}₹${NF[0].format(v)} cr`;
    },
    crPlain: (x) => (ok(x) ? NF[0].format(x) : '–'),
    pct: (x, dp = 1) => (ok(x) ? (x * 100).toFixed(dp) + '%' : '–'),
    spct: (x, dp = 1) => (ok(x) ? (x >= 0 ? '+' : '−') + Math.abs(x * 100).toFixed(dp) + '%' : '–'),
    x: (x, dp = 1) => (ok(x) ? x.toFixed(dp) + 'x' : 'n.m.'),
    date: (iso) => {
      if (!iso) return '–';
      const d = new Date(iso.length === 10 ? iso + 'T00:00:00Z' : iso);
      return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
    },
    fy: (fy) => 'FY' + String(fy).slice(2),
    monthYear: (iso) => new Date(iso + 'T00:00:00Z').toLocaleDateString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' }),
    /** whole rupees, for axis ticks */
    rupees: (x) => (ok(x) ? '₹' + NF[0].format(x) : '–'),
  };
  const esc = VDL.esc = (s) => String(s).replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
  VDL.deltaClass = (x) => (!ok(x) ? '' : x >= 0 ? 'delta-up' : 'delta-down');
  VDL.arrow = (x) => (!ok(x) ? '' : x >= 0 ? '▲' : '▼');

  /* ---------------- Per-company working model ---------------- */
  const models = {};
  VDL.model = function (ticker) {
    if (!models[ticker]) {
      const c = VDL.byTicker[ticker];
      models[ticker] = {
        c,
        a: clone(c.dcf.assumptions),
        cap: { gsec: D.market.gsec_10y, erp: D.market.erp, beta_u: VDL.sectorBeta[c.sector] },
        waccManual: false,
        lbo: c.lbo.result ? clone(c.lbo.assumptions) : null,
        lboPremium: D.market.lbo_premium,
        lboTie: true,
      };
    }
    return models[ticker];
  };
  VDL.resetModel = (ticker) => { delete models[ticker]; return VDL.model(ticker); };

  VDL.cost = function (m) {
    const mkt = Object.assign({}, D.market, { gsec_10y: m.cap.gsec, erp: m.cap.erp });
    return E.companyWacc(mkt, m.c.market_cap, m.c.latest_bs.debt, m.c.history.interest_coverage, m.cap.beta_u);
  };
  /** Push the cost-of-capital build into the DCF assumptions. */
  VDL.applyCost = function (m) {
    const cost = VDL.cost(m);
    m.a.wacc = cost.wacc;
    m.a.cost_equity = cost.cost_equity;
    m.waccManual = false;
    return cost;
  };
  VDL.dcf = function (m) {
    try { return E.runDcf(m.a); } catch (e) { return null; }
  };
  VDL.netDebtBridge = (c) => c.latest_bs.debt + c.latest_bs.minority - c.latest_bs.cash - c.latest_bs.lt_investments;

  /* ---------------- DOM helpers ---------------- */
  VDL.$ = (id) => document.getElementById(id);
  VDL.statBox = (label, value, sub, cls = '') =>
    `<div class="stat-box ${cls}"><div class="stat-label">${label}</div><div class="stat-value">${value}</div>${sub ? `<div class="stat-sub">${sub}</div>` : ''}</div>`;
  VDL.status = (kind, label) => {
    const ico = { pass: '✓', warn: '!', fail: '×' }[kind];
    return `<span class="status ${kind}"><span class="ico" aria-hidden="true">${ico}</span>${label}</span>`;
  };

  /**
   * Range control. o: {label, min, max, step, value, fmt, hint, onInput}
   * Returns {set(value), input}.
   */
  VDL.slider = function (host, o) {
    const wrap = document.createElement('div');
    wrap.className = 'control-group';
    wrap.innerHTML =
      `<div class="control-label"><span>${o.label}</span><span class="value"></span></div>` +
      `<input type="range" min="${o.min}" max="${o.max}" step="${o.step}" aria-label="${esc(o.label)}">` +
      (o.hint ? `<div class="control-hint">${o.hint}</div>` : '');
    const input = wrap.querySelector('input');
    const out = wrap.querySelector('.value');
    // The thumb snaps to the step grid, but the model keeps the exact value
    // until the user moves the control, so the label shows the exact value.
    let exact = o.value;
    const paint = () => {
      const v = exact !== null ? exact : Number(input.value);
      out.textContent = o.fmt(v);
      const p = Math.min(100, Math.max(0, ((v - o.min) / (o.max - o.min)) * 100));
      input.style.background = `linear-gradient(90deg, #00f0ff ${p}%, rgba(255,255,255,0.10) ${p}%)`;
    };
    input.value = Math.min(o.max, Math.max(o.min, o.value));
    input.addEventListener('input', () => { exact = null; paint(); o.onInput(Number(input.value)); });
    paint();
    host.appendChild(wrap);
    return {
      input,
      set(v) { exact = v; input.value = Math.min(o.max, Math.max(o.min, v)); paint(); },
      disable(flag) { input.disabled = flag; },
    };
  };

  /* ---------------- Heat cells ---------------- */
  /** Diverging blue (above) / red (below) wash around a neutral midpoint; t in [-1, 1]. */
  VDL.divergingBg = function (t) {
    if (!ok(t)) return 'var(--surface-3)';
    const a = 0.10 + 0.55 * Math.min(1, Math.abs(t));
    if (Math.abs(t) < 0.02) return 'rgba(107,122,143,0.22)';
    return t > 0 ? `rgba(57,135,229,${a.toFixed(3)})` : `rgba(230,103,103,${a.toFixed(3)})`;
  };

  /* ---------------- Charts ---------------- */
  if (window.Chart) {
    Chart.defaults.color = COL.ink2;
    Chart.defaults.font.family = '-apple-system, "Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size = 11;
    Chart.defaults.animation = false;
    Chart.defaults.plugins.legend.display = false;
    Chart.defaults.plugins.tooltip.backgroundColor = '#0b0e15';
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(0,240,255,0.25)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.titleColor = COL.ink;
    Chart.defaults.plugins.tooltip.bodyColor = COL.ink2;
    Chart.defaults.plugins.tooltip.padding = 10;
    Chart.defaults.plugins.tooltip.bodyFont = { family: MONO, size: 11 };
    Chart.defaults.plugins.tooltip.displayColors = false;

    // Value labels on bars (ink text, never the series colour).
    Chart.register({
      id: 'valueLabels',
      afterDatasetsDraw(chart, _args, opts) {
        if (!opts || !opts.fmt) return;
        const ctx = chart.ctx;
        ctx.save();
        ctx.font = `600 10.5px ${MONO}`;
        ctx.fillStyle = COL.ink;
        const horizontal = chart.options.indexAxis === 'y';
        chart.data.datasets.forEach((ds, di) => {
          const meta = chart.getDatasetMeta(di);
          if (meta.hidden || ds.noLabels || meta.type !== 'bar') return;
          meta.data.forEach((bar, i) => {
            const txt = opts.fmt(ds.data[i], i, ds);
            if (!txt) return;
            if (horizontal) {
              ctx.textAlign = 'left';
              ctx.textBaseline = 'middle';
              ctx.fillText(txt, Math.max(bar.x, bar.base) + 6, bar.y);
            } else {
              ctx.textAlign = 'center';
              ctx.textBaseline = 'bottom';
              ctx.fillText(txt, bar.x, Math.min(bar.y, bar.base) - 4);
            }
          });
        });
        ctx.restore();
      },
    });

    // Vertical reference line with a label (used for the market price).
    Chart.register({
      id: 'refLine',
      afterDatasetsDraw(chart, _args, opts) {
        if (!opts || !ok(opts.value)) return;
        const { ctx, chartArea: area, scales } = chart;
        const horizontal = chart.options.indexAxis === 'y';
        ctx.save();
        ctx.strokeStyle = COL.ink;
        ctx.fillStyle = COL.ink;
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 4]);
        ctx.font = `600 10.5px ${MONO}`;
        ctx.beginPath();
        if (horizontal) {
          const x = scales.x.getPixelForValue(opts.value);
          if (x < area.left || x > area.right) { ctx.restore(); return; }
          ctx.moveTo(x, area.top); ctx.lineTo(x, area.bottom); ctx.stroke();
          ctx.setLineDash([]);
          ctx.textAlign = x > area.right - 90 ? 'right' : 'left';
          ctx.textBaseline = 'top';
          ctx.fillText(opts.label || '', x + (ctx.textAlign === 'left' ? 6 : -6), area.top + 2);
        } else {
          const y = scales.y.getPixelForValue(opts.value);
          if (y < area.top || y > area.bottom) { ctx.restore(); return; }
          ctx.moveTo(area.left, y); ctx.lineTo(area.right, y); ctx.stroke();
          ctx.setLineDash([]);
          ctx.textAlign = 'right';
          ctx.textBaseline = 'bottom';
          ctx.fillText(opts.label || '', area.right - 4, y - 4);
        }
        ctx.restore();
      },
    });
  }

  VDL.chart = function (canvasId, config) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || !window.Chart) return null;
    if (VDL.charts[canvasId]) VDL.charts[canvasId].destroy();
    VDL.charts[canvasId] = new Chart(canvas, config);
    return VDL.charts[canvasId];
  };

  VDL.axis = (o = {}) => Object.assign({
    grid: { color: COL.grid, drawTicks: false },
    border: { color: COL.axis },
    ticks: { color: COL.muted, padding: 6, font: { family: MONO, size: 10 } },
  }, o);

  /**
   * Waterfall: steps [{label, value, kind: 'total' | 'delta'}] to floating bars.
   * Totals are neutral; additions blue; deductions red.
   */
  VDL.waterfall = function (steps) {
    let running = 0;
    const data = [], colors = [], values = [];
    for (const s of steps) {
      if (s.kind === 'total') { data.push([0, s.value]); running = s.value; colors.push(COL.neutral); }
      else { data.push([running, running + s.value]); running += s.value; colors.push(s.value >= 0 ? COL.s1 : COL.neg); }
      values.push(s.value);
    }
    return { labels: steps.map((s) => s.label), data, colors, values, kinds: steps.map((s) => s.kind) };
  };

  VDL.waterfallChart = function (canvasId, steps, fmt) {
    const w = VDL.waterfall(steps);
    return VDL.chart(canvasId, {
      type: 'bar',
      data: { labels: w.labels, datasets: [{ data: w.data, backgroundColor: w.colors, borderRadius: 3, borderSkipped: false, maxBarThickness: 46 }] },
      options: {
        maintainAspectRatio: false,
        layout: { padding: { top: 18 } },
        scales: {
          x: VDL.axis({ grid: { display: false }, ticks: { color: COL.ink2, font: { size: 10.5 }, maxRotation: 0, autoSkip: false } }),
          y: VDL.axis({ ticks: { color: COL.muted, font: { family: MONO, size: 10 }, callback: (v) => fmt(v) } }),
        },
        plugins: {
          valueLabels: { fmt: (_d, i) => (w.kinds[i] === 'total' ? fmt(w.values[i]) : (w.values[i] >= 0 ? '+' : '−') + fmt(Math.abs(w.values[i])).replace('−', '')) },
          tooltip: { callbacks: { label: (ctx) => `${w.kinds[ctx.dataIndex] === 'total' ? 'Level' : 'Change'}: ${fmt(w.values[ctx.dataIndex])}` } },
        },
      },
    });
  };
})();
