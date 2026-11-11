# Build plan and status

Working checklist for this repo and its sibling `verifiable-research-desk`
(checked out next to this one). Any session can resume from here: read this
file, run the checks under "How to verify", then continue with the first
unchecked item.

## Valuation & Deal Lab (this repo)

- [x] Engine: `fin`, `wacc`, `dcf`, `comps`, `lbo`, `merger`, `statements`, `defaults`
- [x] Test suite against closed forms and accounting identities (`tests/`)
- [x] Pipeline: keyless fetch, weekly fundamentals snapshots, data gates, engine invariants
- [x] Browser engine (`docs/assets/js/engine.js`) and Python/JS parity test (`tests/parity.js`)
- [x] Site: overview, cost of capital, DCF, comps, LBO, M&A, football field, model integrity
- [x] Valuation memo (print-ready one-pager per company)
- [x] GitHub Actions: CI (tests + parity) and weekday data refresh
- [x] README
- [x] Published 2026-11-11: https://nnd1106.github.io/valuation-deal-lab/ (refresh workflow run once by hand, green)
- [ ] Confirm the scheduled refresh runs green for a week (GitHub delays cron jobs by hours; that is normal)

## Verifiable Research Desk (sibling repo)

- [x] Independent re-validation of the Portfolio Construction Lab (33 checks)
- [x] Independent re-validation of this lab (22 checks, DCF re-valued by economic profit)
- [x] Forecast ledger: hash-chained forecasts and outcomes, scoring, walk-forward backtests
- [x] Hub site, run tear sheet, in-browser chain verification
- [x] GitHub Actions: weekday desk run (commit first, then fail on a failed check)
- [x] Published 2026-11-11: https://nnd1106.github.io/verifiable-research-desk/ (desk workflow run once by hand, green;
      both sources now read as "published")
- [ ] Watch the first scored outcomes arrive (risk forecasts: next session; valuation calls: 9 Dec 2026)
- [x] Both projects added as cards on the portfolio homepage (`nnd1106.github.io`), 2026-11-11

## How to verify

```bash
# this repo
python -m pytest tests -q
python pipeline/build_data.py --refresh never
node tests/parity.js

# sibling repo
cd ../verifiable-research-desk
python -m pytest tests -q
python run.py --assert-clean
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
- Capex fades with growth to a steady state: the lower of history scaled to
  terminal growth and what the terminal value assumes, never below depreciation.
- The DCF values the firm at the last fiscal year-end and rolls equity forward
  to the valuation date at the cost of equity, net of dividends paid since.
- LBO cash shortfalls draw on a revolver at the senior rate.
- No runtime AI and no API keys anywhere. Everything is deterministic.
- The desk never imports code from the projects it validates, and its ledger
  is append-only: never rewrite or re-order `docs/ledger/*.jsonl`.

## Maintenance notes

- `pipeline/config.py` holds the G-sec yield and equity risk premium with
  their sources and dates. The build warns when they are stale (45 and 400
  days). Update the value, the date and the source text together.
- If the engine changes, change `engine/*.py` and `docs/assets/js/engine.js`
  together; `tests/parity.js` fails until they agree.
