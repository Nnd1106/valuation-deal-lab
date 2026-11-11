# Valuation & Deal Lab

An investment-banking valuation platform on real Indian large-cap data, built the way a deal team works: **cost of capital → DCF → trading comps → LBO → M&A accretion/dilution → football field**, for 24 companies across five sectors.

What makes it different from a spreadsheet model or a dashboard is that **every number is verifiable**:

- the valuation engine is a tested library, checked against closed-form results it has to reproduce exactly;
- real data has to pass quality gates before anything is published, and a failed build publishes nothing;
- the engine that runs in your browser is compared value for value with the Python engine on every build, and again live on the page.

**Live:** https://nnd1106.github.io/valuation-deal-lab/

Dark finance-terminal UI in vanilla HTML/CSS/JS + [Chart.js](https://www.chartjs.org/). No framework, no build step, no backend, and **no API keys anywhere**. I built it independently, applying MBA coursework in Business Valuation, Investment Analysis and Financial Risk Management to real market data. It is the companion to my [Portfolio Construction Lab](https://github.com/Nnd1106/portfolio-construction-lab).

---

## The eight modules

| # | Module | What it does |
|---|---|---|
| 01 | **Overview** | Three lenses on value (market price, DCF baseline, peer-implied), a five-year price chart, standardised financial history, and a reverse DCF: the revenue growth and the margin that today's price requires. |
| 02 | **Cost of Capital** | A line-by-line WACC build. Risk-free rate = 10-year G-sec yield less India's sovereign default spread; **bottom-up sector beta** (median of peers' unlevered betas, relevered at the company's own D/E); cost of debt from a synthetic rating on interest coverage. Every input is sourced and adjustable. |
| 03 | **DCF** | Ten-year unlevered DCF. Growth holds, then fades; the margin reverts to the company's own average; growth capex shrinks as growth slows; terminal value by the **value-driver formula** `NOPAT × (1 − g/RONIC) / (WACC − g)`. Mid-year discounting, an EV-to-equity bridge, a WACC × terminal-growth heatmap, and Bear/Base/Bull presets. |
| 04 | **Comps** | EV/EBITDA, EV/EBIT, EV/Sales, P/E and P/B on trailing-twelve-month figures against the sector peer group, with quartiles and the value each peer multiple implies. |
| 05 | **LBO** | Sources and uses, a senior term loan with mandatory amortisation and a cash sweep, subordinated notes, an interest circularity solved by iteration, a revolver for shortfalls, IRR and money multiple, an exact value-creation bridge and an IRR sensitivity grid. |
| 06 | **M&A** | Accretion/dilution for any acquirer and target in the universe: cash/stock mix, balance-sheet cash versus new debt, synergies, purchase price allocation, break-even synergies, contribution analysis and a premium × cash-mix grid. |
| 07 | **Football Field** | Every method on one price axis against the market price: 52-week range, DCF, three comps ranges, and the price a sponsor could pay for a 15–25% IRR. Updates with every slider. |
| 08 | **Model Integrity** | Re-runs the parity check in your browser, shows the data gates for the selected company, lists every assumption with its source, and states the model's limitations. |

**Valuation Memo.** A header button turns the current state of the sliders into a one-page, print-ready memo for the selected company.

---

## How the numbers are verified

### 1. The engine is tested against results it must reproduce exactly

`engine/` is a pure-Python library with no I/O. `tests/` holds 125 tests; the property tests run each claim over thousands of randomly generated inputs ([Hypothesis](https://hypothesis.readthedocs.io/)). A sample of what is proved:

| Model | Property |
|---|---|
| DCF | A firm growing at a constant rate equals the Gordon growth formula for **any** forecast horizon. |
| DCF | Mid-year discounting scales enterprise value by exactly `(1 + WACC)^0.5`. |
| DCF | With RONIC = WACC the terminal value equals `NOPAT / WACC`: growth adds value only when RONIC exceeds WACC. |
| DCF | Rolling equity value forward preserves present value; the reverse DCF recovers the growth rate that produced a price. |
| LBO | An unlevered, no-growth deal has a closed-form IRR; cash is conserved through the debt schedule; the value-creation bridge sums exactly to the equity gain. |
| M&A | An all-stock deal is accretive **if and only if** the acquirer's P/E exceeds the offer P/E; a debt-funded cash deal if and only if the target's earnings yield beats the after-tax cost of debt. |
| M&A | Break-even synergies make the deal exactly EPS-neutral. |
| WACC | Regression betas match an independent least-squares solver; every rating band is checked at its boundary. |
| Comps | Valuing a company at its own multiple returns its own price. |

### 2. Real data passes gates before it is published

`pipeline/build_data.py` runs 19 gates per company and then re-checks model identities on the real numbers. Hard failures exclude a company; warnings are published next to its numbers. If too few companies survive, a peer group gets too thin, or any identity breaks, the build exits non-zero, **nothing is written, and the last good data stays live**.

Two gates exist because of problems found while building this:

- **Reporting currency.** The provider tags some Indian companies as USD reporters when their statements are in rupees, and vice versa. The pipeline ignores the tag and infers the currency by comparing statement EPS with rupee EPS. Infosys really does report in USD, so its flows are converted at period-average USDINR and its balances at period-end.
- **Operating income.** The provider files about 14% of HCL Technologies' revenue of real operating costs under "other non-operating" items, which overstates its margin at 31% against roughly 17%. Negative amounts on that line are therefore treated as operating costs, and operating income is cross-checked against an independent rebuild from pre-tax profit.

### 3. The browser engine is the same model

`docs/assets/js/engine.js` mirrors the Python engine line for line. `tests/parity.js` recomputes every published number in Node from the published assumptions and fails on any relative difference above 1e-9 (currently 9,250 values across 24 companies, largest difference about 2e-16). The **Model Integrity** tab runs the same comparison live on your machine, so the sliders drive the tested model and not an approximation of it.

```bash
pip install -r requirements.txt
python -m pytest tests -q              # engine tests, plus parity if Node is installed
python pipeline/build_data.py          # fetch, gate, value, publish
node tests/parity.js                   # browser engine vs Python engine
```

---

## Universe

24 non-financial Indian large caps in five peer groups. Banks, NBFCs and groups with a consolidated captive finance arm are excluded on purpose: free cash flow to the firm and EV multiples are not meaningful for them.

| Sector | Companies |
|---|---|
| IT Services | TCS, Infosys, HCL Technologies, Wipro, Tech Mahindra |
| Consumer Staples | Hindustan Unilever, ITC, Britannia, Dabur, Marico |
| Pharmaceuticals | Sun Pharma, Dr. Reddy's, Cipla, Lupin, Zydus Lifesciences |
| Automobiles | Maruti Suzuki, Bajaj Auto, Eicher Motors, Hero MotoCorp |
| Cement | UltraTech, Shree Cement, Ambuja Cements, Dalmia Bharat, JK Cement |

## Architecture

```
GitHub Actions (weekdays 6:00 PM IST = cron "30 12 * * 1-5")
  ├─ pytest                      engine against closed forms
  ├─ pipeline/build_data.py
  │    ├─ fetch.py               yfinance (keyless): prices daily, statements snapshotted weekly
  │    ├─ engine/statements.py   raw statements → one schema, INR crore, currency verified
  │    ├─ engine/defaults.py     history → documented default assumptions
  │    ├─ engine/{wacc,dcf,comps,lbo,merger}.py
  │    └─ gates + invariants     fail the run → nothing committed
  ├─ node tests/parity.js        browser engine vs the numbers just published
  └─ commits docs/data/deal-lab-data.{json,js} and data/fundamentals/*.json

GitHub Pages serves /docs  →  vanilla JS reads window.VDL_DATA and computes with engine.js
                              (no network calls from the browser besides the Chart.js CDN)
```

Statements are snapshotted in `data/fundamentals/` so that a refresh is reviewable as a diff and a bad download can never silently replace good data.

## Key modelling choices

- **EBIT is operating income before other and investment income.** Cash, short-term investments and long-term financial investments are treated as non-operating: added back at book value in the DCF bridge and netted out of enterprise value in every multiple. This matters for cash-rich companies; Maruti carries long-term investments worth about 15% of its market cap that the provider's own enterprise value ignores.
- **Country risk is counted once.** The equity risk premium (Damodaran) already includes India's country premium, so the risk-free rate is the G-sec yield less the sovereign default spread, not the raw G-sec yield.
- **Bottom-up beta.** A single company's five-year weekly beta has a standard error of around 0.1, so the sector median of unlevered betas is used and relevered at each company's own capital structure.
- **Terminal growth has to be paid for.** The value-driver formula ties terminal growth to reinvestment. The default RONIC = WACC means growth beyond year ten adds no value, the conservative convention; the slider lets you give a business a lasting advantage.
- **Capex converges to a steady state.** Growth capex shrinks in proportion to growth, is capped at the reinvestment the terminal value itself assumes, and never ends below depreciation. Without this, a company in an expansion phase is valued as if the expansion never ends.
- **Valuation date.** The firm is valued at the last fiscal year-end, where the balance sheet is known, and equity is rolled forward to today at the cost of equity, net of dividends paid since.
- **LBO shortfalls are not free.** If cash flow cannot cover debt service, the gap is drawn on a revolver at the senior rate and repaid before any sweep.

## How to read the output

The default DCF assumptions are **mechanical, rules-based starting points derived from three to four years of history. They are not forecasts.** Under those conservative defaults most of the universe screens below its market price, in some sectors far below. That is a statement about the expectations built into Indian large-cap prices, not a recommendation: the Overview tab leads with the growth and margin the price requires for exactly this reason, and every assumption is a slider.

## Limitations

- Statements come from a free data provider, not audited filings. The gates catch structural errors, not every misstatement.
- Default forecasts ignore guidance, capacity plans and everything else an analyst would know.
- Financial investments enter at book value; associates and joint ventures worth more than their carrying amount are understated.
- The G-sec yield and the equity risk premium have no keyless source, so they are fixed in `pipeline/config.py` with their source and date, and the build warns when they go stale.
- The LBO ignores India-specific limits on acquisition financing and interest deductibility; the M&A model ignores deferred tax on the purchase price allocation.
- The M&A pairs offered as presets illustrate the mechanics only and do not suggest any transaction.

## Sources

- Prices and statements: Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance)
- Equity risk premium, country default spread, synthetic rating spreads: Aswath Damodaran, NYU Stern ([data page](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html))
- Method: Koller, Goedhart and Wessels, *Valuation* (value-driver formula, RONIC); Damodaran, *Investment Valuation* (bottom-up betas, synthetic ratings); Rosenbaum and Pearl, *Investment Banking* (comps, LBO, M&A mechanics)

---

*Educational project. Nothing here is investment advice or a recommendation to buy or sell any security.*
