# Build plan and status

Working checklist for this repo and its sibling `verifiable-research-desk`.
Any session can resume from here: read this file, run the checks under
"How to verify", then continue with the first unchecked item.

## Valuation & Deal Lab (this repo)

- [x] Engine: `fin`, `wacc`, `dcf`, `comps`, `lbo`, `merger`, `statements`, `defaults`
- [x] Test suite against closed forms and accounting identities (`tests/`)
- [x] Pipeline: keyless fetch, weekly fundamentals snapshots, data gates, engine invariants
- [x] Browser engine (`docs/assets/js/engine.js`) and Python/JS parity test (`tests/parity.js`)
- [ ] Site: company, cost of capital, DCF, comps, LBO, M&A, football field, model integrity
- [ ] Valuation memo (print-ready one-pager per company)
- [ ] GitHub Actions: CI (tests + parity) and weekday data refresh
- [ ] README and model documentation
- [ ] Publish to GitHub Pages (needs owner approval before the first push)

### Site design already decided (not built yet)

Single page `docs/index.html`, vanilla JS + Chart.js, same dark theme, tokens and
signature gradient as `portfolio-construction-lab/docs/assets/css/style.css`.
It reads `window.VDL_DATA` from `docs/data/deal-lab-data.js` and computes with
`docs/assets/js/engine.js` (already parity-tested; do not re-implement any math).
Tabs: 01 Overview (snapshot, price chart, statements, "what the price implies"),
02 Cost of Capital, 03 DCF (sliders, bridge, WACC x g heatmap, reverse DCF),
04 Comps, 05 LBO, 06 M&A, 07 Football Field, 08 Model Integrity (re-run parity
in the browser, gates, sources). Chart colours: validated dark categorical
slots `#3987e5 #d95926 #199e70 #c98500 #d55181` on surface `#0f131c`; status
colours `#0ca30c #fab219 #ec835a #d03b3b` with icon and label.
Frame the DCF as a conservative rules-based baseline and lead with the
market-implied growth and margin, because most names screen below market.

## Verifiable Research Desk (sibling repo)

- [ ] Independent re-validation of the Portfolio Construction Lab's published numbers
- [ ] Independent re-validation of this lab's published numbers
- [ ] Forecast ledger: hash-chained, git-timestamped forecasts and scoring
- [ ] Hub site linking all three projects, weekly tear sheets

## How to verify

```bash
python -m pytest tests -q
python pipeline/build_data.py --refresh never
node tests/parity.js
```

## Decisions already made (do not relitigate)

- Universe: 24 non-financial Indian large caps in 5 peer groups (`pipeline/config.py`).
  Banks and groups with captive finance arms are excluded on purpose.
- EBIT is operating income before other income; negative "other non-operating"
  items are treated as operating costs (provider misfiles them, e.g. HCL Tech).
- Enterprise value nets cash, short-term investments and long-term financial
  investments, consistently in the DCF bridge and in every multiple.
- Risk-free rate = 10-year G-sec yield less the sovereign default spread; the
  equity risk premium already includes India's country premium (Damodaran).
- Terminal value uses the value-driver formula with RONIC = WACC by default.
- The DCF values the firm at the last fiscal year-end and rolls equity forward
  to the valuation date at the cost of equity, net of dividends paid since.
- No runtime AI and no API keys anywhere. Everything is deterministic.
