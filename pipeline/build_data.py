"""build_data.py: fetch, validate, value and publish.

    python pipeline/build_data.py [--refresh auto|always|never]

Writes docs/data/deal-lab-data.json and .js. Exits non-zero, writing nothing,
when the data or the engine fails a gate, so a bad run can never replace the
last good published file.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C  # noqa: E402
import fetch as F  # noqa: E402
from gates import Gates, close, finite  # noqa: E402
from engine import __version__ as ENGINE_VERSION  # noqa: E402
from engine import comps, dcf, defaults, lbo, merger, statements, wacc as W  # noqa: E402

OUT_DIR = os.path.join(ROOT, "docs", "data")
SCHEMA_VERSION = 1


# ---------------------------------------------------------------- helpers

def clean(obj):
    """Make an object JSON-safe: numpy scalars to Python, NaN/inf to None."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return v if math.isfinite(v) else None
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def weekly_returns(adj_close: pd.Series, last_date: pd.Timestamp) -> pd.Series:
    """Friday-to-Friday total returns over completed weeks only."""
    weekly = adj_close.resample("W-FRI").last().dropna()
    weekly = weekly[weekly.index <= last_date]
    return weekly.pct_change().dropna()


def make_fx(usdinr: pd.Series):
    def fx_at(iso: str) -> float:
        s = usdinr[usdinr.index <= pd.Timestamp(iso)]
        if s.empty:
            raise ValueError(f"no USDINR rate on or before {iso}")
        return float(s.iloc[-1])

    def fx_avg(start_iso: str, end_iso: str) -> float:
        s = usdinr[(usdinr.index >= pd.Timestamp(start_iso)) & (usdinr.index <= pd.Timestamp(end_iso))]
        if len(s) < 20:
            raise ValueError(f"too few USDINR observations between {start_iso} and {end_iso}")
        return float(s.mean())

    return fx_avg, fx_at


def usable(raw: dict | None, usdinr_spot: float, fx_avg, fx_at) -> bool:
    if not raw:
        return False
    try:
        norm = statements.normalize(raw, usdinr_spot, fx_avg, fx_at)
    except Exception:
        return False
    return len(norm["annual"]) >= C.MIN_FISCAL_YEARS


def get_raw(ticker: str, mode: str, usdinr_spot: float, fx_avg, fx_at) -> tuple[dict | None, str]:
    """Snapshot for a ticker, refreshed when stale. A fresh download only
    replaces the stored snapshot if it is at least as usable."""
    snap = F.load_snapshot(ticker)
    age = F.snapshot_age_days(snap)
    need = snap is None or mode == "always" or (mode == "auto" and age > C.FUNDAMENTALS_MAX_AGE_DAYS)
    if not need:
        return snap, "snapshot"
    fresh = F.fetch_fundamentals(ticker)
    time.sleep(0.6)
    if usable(fresh, usdinr_spot, fx_avg, fx_at):
        F.save_snapshot(fresh)
        return fresh, "refreshed"
    if snap is not None:
        print(f"  ~ {ticker}: fresh download unusable, keeping snapshot from {snap.get('fetched_utc')}")
        return snap, "snapshot (refresh failed)"
    return None, "unavailable"


# ---------------------------------------------------------------- stage 1: data

def stage_data(ticker: str, raw: dict | None, hist: pd.DataFrame, market_weekly: pd.Series,
               valuation_date: pd.Timestamp, usdinr_spot: float, fx_avg, fx_at) -> dict:
    name, sector = C.UNIVERSE[ticker]
    g = Gates()
    out = {"ticker": ticker, "name": name, "sector": sector, "gates": g, "flags": []}
    tax = C.MARKET["tax_rate"]

    if not g.check("statements_available", raw is not None, "fundamentals could not be downloaded"):
        return out
    norm = statements.normalize(raw, usdinr_spot, fx_avg, fx_at)
    out["flags"] += norm["flags"]
    out["currency_reported"] = norm["currency"]
    out["snapshot_utc"] = raw.get("fetched_utc")
    if not g.check("currency_verified", norm["currency"] is not None,
                   "statement currency checked against rupee EPS"):
        return out
    annual = norm["annual"]
    if not g.check("fiscal_years", len(annual) >= C.MIN_FISCAL_YEARS,
                   f"{len(annual)} consecutive complete fiscal years (need {C.MIN_FISCAL_YEARS})"):
        return out
    fye = annual[-1]
    fye_date = pd.Timestamp(fye["period_end"])
    months_old = (valuation_date - fye_date).days / 30.44
    g.check("statements_fresh", months_old <= 15.0, f"last fiscal year ended {months_old:.1f} months ago")

    worst = max(abs(r["total_assets"] - r["total_liabilities"] - r["equity"] - r["minority"]) / r["total_assets"]
                for r in annual)
    g.check("balance_sheet_balances", worst <= 0.01, f"largest imbalance {worst:.3%} of total assets")
    g.check("positive_operations", fye["revenue"] > 0 and fye["ebit"] > 0 and fye["ebitda"] > 0,
            "revenue, EBIT and EBITDA positive in the last fiscal year")
    rebuilt = fye.get("ebit_bottom_up")
    ebit_gap = None if rebuilt is None else abs(fye["ebit"] - rebuilt) / fye["revenue"]
    g.check("operating_income_reconciles", ebit_gap is not None and ebit_gap <= 0.05,
            "operating income vs a rebuild from pre-tax profit: " +
            ("n/a" if ebit_gap is None else f"{ebit_gap:.1%} of revenue apart"), level="warn")
    reclassified = (fye["ebit_reported"] - fye["ebit"]) / fye["revenue"]
    if reclassified > 0.01:
        out["flags"].append(f"{reclassified:.1%} of revenue that the data provider files under other "
                            "non-operating items is treated as operating cost")
    g.check("non_operating_assets_bounded",
            all(r["cash"] + r["lt_investments"] <= r["total_assets"] for r in annual),
            "cash and investments do not exceed total assets")
    eps_gap = None
    if fye.get("eps") and fye.get("shares_diluted"):
        eps_gap = abs(fye["net_income"] / fye["shares_diluted"] - fye["eps"]) / abs(fye["eps"])
    g.check("eps_consistent", eps_gap is not None and eps_gap <= 0.05,
            "net income / diluted shares vs reported EPS: " +
            ("n/a" if eps_gap is None else f"{eps_gap:.2%} apart"), level="warn")

    bs = norm["latest_bs"] or fye
    ltm = norm["ltm"]
    if not g.check("ltm_available", ltm is not None,
                   "four consecutive complete quarters for LTM figures", level="warn"):
        out["flags"].append("LTM not available: trailing figures use the last fiscal year")

    # ---- prices
    if not g.check("price_history", not hist.empty, "price history downloaded"):
        return out
    px = hist[hist.index <= valuation_date]
    last_date = px.index[-1]
    price = float(px["Close"].iloc[-1])
    g.check("price_fresh", (valuation_date - last_date).days <= 7,
            f"last close {last_date.date()} vs valuation date {valuation_date.date()}")
    year = px["Close"].iloc[-252:]

    info_shares = (raw.get("info") or {}).get("sharesOutstanding")
    bs_shares = bs["shares_out"]
    shares = info_shares / statements.CRORE if info_shares else bs_shares
    gap = abs(shares - bs_shares) / bs_shares
    if not g.check("share_count_consistent", gap <= 0.10,
                   f"quoted share count vs latest balance sheet: {gap:.2%} apart", level="warn"):
        shares = bs_shares
        out["flags"].append("share count taken from the latest balance sheet (quote differed by more than 10%)")
    market_cap = price * shares

    # ---- beta
    stock_weekly = weekly_returns(px["AdjClose"], valuation_date)
    joined = pd.concat([stock_weekly, market_weekly], axis=1, join="inner").dropna().iloc[-C.BETA_WINDOW_WEEKS:]
    beta = None
    if g.check("beta_sample", len(joined) >= C.BETA_MIN_WEEKS,
               f"{len(joined)} weekly observations (need {C.BETA_MIN_WEEKS})"):
        reg = W.beta_ols(list(joined.iloc[:, 0]), list(joined.iloc[:, 1]))
        beta = {"raw": reg["beta"], "se": reg["se"], "r2": reg["r2"], "n": reg["n"],
                "blume": W.blume_adjust(reg["beta"]),
                "window": f"{joined.index[0].date()} to {joined.index[-1].date()}, weekly vs Nifty 50"}

    hist_metrics = statements.history_metrics(annual, tax)
    leverage = fye["debt"] / fye["ebitda"] if fye["ebitda"] > 0 else None
    g.check("leverage_plausible", leverage is not None and leverage <= 6.0,
            "debt / EBITDA " + ("n/a" if leverage is None else f"{leverage:.1f}x") +
            " (very high leverage can mean a consolidated financing arm)", level="warn")

    divs = px["Dividends"]
    divs = divs[(divs.index > fye_date) & (divs > 0)]
    dividends_since_fye = [[(d - fye_date).days / 365.25, float(v)] for d, v in divs.items()]

    weekly_close = px["Close"].resample("W-FRI").last().dropna().iloc[-C.BETA_WINDOW_WEEKS:]
    out.update({
        "annual": annual, "ltm": ltm, "latest_bs": bs, "history": hist_metrics, "fye": fye,
        "price": price, "price_date": str(last_date.date()), "shares": shares, "market_cap": market_cap,
        "hi52": float(year.max()), "lo52": float(year.min()), "beta": beta,
        "years_since_fye": (valuation_date - fye_date).days / 365.25,
        "dividends_since_fye": dividends_since_fye,
        "prices": {"dates": [str(d.date()) for d in weekly_close.index],
                   "close": [round(float(v), 2) for v in weekly_close.values]},
    })
    return out


# ---------------------------------------------------------------- stage 2: valuation

def trailing(c: dict) -> dict:
    """Trailing operating figures: LTM when available, else the last fiscal year."""
    src = c["ltm"] or c["fye"]
    eps = src.get("eps")
    if eps is None:
        eps = src["net_income"] / c["shares"]
    return {"basis": "LTM to " + src["period_end"] if c["ltm"] else "FY" + str(c["fye"]["fy"]),
            "revenue": src["revenue"], "ebitda": src["ebitda"], "ebit": src["ebit"],
            "net_income": src["net_income"], "eps": eps}


def comps_input(c: dict) -> dict:
    t, bs = c["trailing"], c["latest_bs"]
    return {"price": c["price"], "shares": c["shares"], "debt": bs["debt"], "minority": bs["minority"],
            "cash": bs["cash"], "lt_investments": bs["lt_investments"], "revenue": t["revenue"],
            "ebitda": t["ebitda"], "ebit": t["ebit"], "eps": t["eps"], "book_equity": bs["equity"]}


def stage_value(c: dict, unlevered_beta: float) -> None:
    g: Gates = c["gates"]
    mkt = C.MARKET
    fye, bs = c["fye"], c["latest_bs"]
    c["trailing"] = trailing(c)

    cost = defaults.company_wacc(mkt, c["market_cap"], bs["debt"], c["history"]["interest_coverage"], unlevered_beta)
    c["cost"] = cost
    a = defaults.default_dcf(fye, c["history"], cost, mkt, c["shares"],
                             c["years_since_fye"], c["dividends_since_fye"])
    raw_nwc = c["history"]["nwc_pct"]
    g.check("working_capital_ratio_in_bounds", a["nwc_pct"] == raw_nwc,
            f"historical NWC/revenue {raw_nwc:.1%} " +
            ("used as is" if a["nwc_pct"] == raw_nwc else f"clamped to {a['nwc_pct']:.0%}"), level="warn")
    ok = g.check("wacc_plausible", 0.06 <= cost["wacc"] <= 0.20 and cost["wacc"] - a["growth_terminal"] >= 0.02,
                 f"WACC {cost['wacc']:.2%}, terminal growth {a['growth_terminal']:.2%}")
    if not ok:
        return

    res = dcf.run_dcf(a)
    g.check("dcf_finite", finite(res["enterprise_value"], res["per_share"]) and res["enterprise_value"] > 0,
            "DCF produced a finite, positive enterprise value")
    if not g.passed:
        return
    g.check("terminal_value_share", res["terminal_share"] <= 0.90,
            f"terminal value is {res['terminal_share']:.0%} of enterprise value", level="warn")

    wacc_values = [a["wacc"] + s for s in C.SENS_WACC_STEPS]
    growth_values = [max(0.0, a["growth_terminal"] + s) for s in C.SENS_GROWTH_STEPS]
    c["dcf"] = {
        "assumptions": a,
        "result": res,
        "sensitivity": {"wacc": wacc_values, "growth_terminal": growth_values,
                        "grid": dcf.sensitivity(a, "wacc", wacc_values, "growth_terminal", growth_values)},
        "implied_growth": dcf.implied_growth(a, c["price"]),
        "implied_margin": dcf.implied_margin(a, c["price"]),
        "upside": res["per_share"] / c["price"] - 1.0,
    }

    # ---- LBO on the same operating case, struck at the trailing date
    t = c["trailing"]
    lbo_a = defaults.default_lbo(a, c["market_cap"], bs, t["ebitda"], mkt)
    lbo_a["base_revenue"] = t["revenue"]
    lbo_a["margin_start"] = t["ebit"] / t["revenue"]
    entry = {"assumptions": lbo_a, "result": None, "note": None, "sponsor_band": None}
    try:
        entry["result"] = lbo.run_lbo(lbo_a)
        own_multiple = comps.multiples(comps_input(c))["ev_ebitda"]
        if own_multiple:
            band_a = dict(lbo_a)
            band_a["exit_multiple"] = own_multiple
            band = {}
            for target in C.LBO_TARGET_IRRS:
                ev = lbo.entry_ev_for_irr(band_a, target)
                band[f"{target:.2f}"] = None if ev is None else (
                    (ev - bs["debt"] - bs["minority"] + bs["cash"] + bs["lt_investments"]) / c["shares"])
            entry["sponsor_band"] = {"exit_multiple": own_multiple, "per_share_at_irr": band}
    except ValueError as exc:
        entry["note"] = str(exc)
    c["lbo"] = entry


def engine_invariants(c: dict) -> list[dict]:
    """Identities that must hold on real data, re-checked on every build."""
    checks = []

    def add(name, ok):
        checks.append({"ticker": c["ticker"], "check": name, "ok": bool(ok)})

    a, res = c["dcf"]["assumptions"], c["dcf"]["result"]
    add("dcf: EV = PV(explicit) + PV(terminal)",
        close(res["enterprise_value"], res["pv_explicit"] + res["pv_terminal"]))
    add("dcf: equity bridge", close(res["equity_value"], res["enterprise_value"] + a["cash"]
                                    + a["lt_investments"] - a["debt"] - a["minority"]))
    add("dcf: final-year growth = terminal growth", close(res["rows"][-1]["growth"], a["growth_terminal"]))
    add("dcf: RONIC = WACC gives TV = NOPAT / WACC",
        close(res["terminal"]["value"], res["terminal"]["nopat_next"] / a["wacc"]))
    grid = c["dcf"]["sensitivity"]["grid"]
    mid = len(grid) // 2
    add("dcf: sensitivity centre = base case", close(grid[mid][mid], res["per_share"]))
    ig = c["dcf"]["implied_growth"]
    if ig is not None:
        b = dict(a)
        b["growth_start"] = ig
        add("reverse dcf: implied growth reprices to market", close(dcf.run_dcf(b)["per_share"], c["price"], rel=1e-7))
    ci = comps_input(c)
    own = comps.multiples(ci)
    for m in comps.ALL_MULTIPLES:
        if own[m] is not None:
            add(f"comps: own {m} reprices to market", close(comps.implied_per_share(ci, m, own[m]), c["price"]))
    r = c["lbo"]["result"]
    if r is not None:
        su = r["sources_uses"]
        add("lbo: sources = uses", close(su["total_sources"], su["total_uses"]))
        add("lbo: value-creation bridge sums", close(sum(r["attribution"].values()), r["value_creation"], rel=1e-8, abs_tol=1e-6))
        total = sum(x["cfads"] for x in r["rows"])
        add("lbo: cash conservation", close(total, su["senior_debt"] - r["rows"][-1]["senior_end"] + r["rows"][-1]["cash_end"], rel=1e-8, abs_tol=1e-6))
    return checks


def company_payload(c: dict, peers: list[dict]) -> dict:
    ci = comps_input(c)
    g: Gates = c["gates"]
    return {
        "ticker": c["ticker"], "name": c["name"], "sector": c["sector"],
        "price": c["price"], "price_date": c["price_date"], "shares": c["shares"],
        "market_cap": c["market_cap"], "hi52": c["hi52"], "lo52": c["lo52"],
        "currency_reported": c["currency_reported"], "snapshot_utc": c["snapshot_utc"],
        "flags": c["flags"],
        "warnings": [w["detail"] for w in g.warnings],
        "gates": g.results,
        "annual": c["annual"], "ltm": c["ltm"], "latest_bs": c["latest_bs"],
        "trailing": c["trailing"], "history": c["history"], "beta": c["beta"], "cost": c["cost"],
        "dcf": c["dcf"], "lbo": c["lbo"],
        "comps": {"input": ci, "multiples": comps.multiples(ci),
                  "peers": [p["ticker"] for p in peers],
                  "valuation": comps.peer_valuation(ci, [comps_input(p) for p in peers])},
        "prices": c["prices"],
    }


def merger_side(c: dict) -> dict:
    return {"price": c["price"], "shares": c["shares"], "net_income": c["trailing"]["net_income"],
            "book_equity": c["latest_bs"]["equity"], "revenue": c["trailing"]["revenue"],
            "pretax_cost_debt": c["cost"]["pretax_cost_debt"]}


# ---------------------------------------------------------------- main

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", choices=("auto", "always", "never"), default="auto")
    args = parser.parse_args()
    mkt = C.MARKET
    now = datetime.now(timezone.utc)

    print("Market index and FX...")
    index_hist = F.fetch_history(C.MARKET_INDEX)
    usd_hist = F.fetch_history(C.USDINR)
    if index_hist.empty or usd_hist.empty:
        print("FATAL: market index or USDINR history unavailable")
        return 1
    valuation_date = index_hist.index[-1]
    market_weekly = weekly_returns(index_hist["AdjClose"], valuation_date)
    usdinr = usd_hist["Close"]
    usdinr_spot = float(usdinr.iloc[-1])
    fx_avg, fx_at = make_fx(usdinr)
    print(f"  valuation date {valuation_date.date()}, USDINR {usdinr_spot:.2f}")

    staged = {}
    for ticker in C.UNIVERSE:
        raw, source = get_raw(ticker, args.refresh, usdinr_spot, fx_avg, fx_at)
        hist = F.fetch_history(ticker + C.EXCHANGE_SUFFIX)
        time.sleep(0.3)
        c = stage_data(ticker, raw, hist, market_weekly, valuation_date, usdinr_spot, fx_avg, fx_at)
        c["fundamentals_source"] = source
        staged[ticker] = c
        status = "ok" if c["gates"].passed else "EXCLUDED: " + "; ".join(f["id"] for f in c["gates"].failed)
        print(f"  {ticker:<11} {source:<26} {status}")

    valid = {t: c for t, c in staged.items() if c["gates"].passed}
    sector_betas = defaults.sector_unlevered_betas(
        [{"sector": c["sector"], "raw_beta": c["beta"]["raw"], "debt": c["latest_bs"]["debt"],
          "market_cap": c["market_cap"]} for c in valid.values()], mkt["tax_rate"])
    for c in valid.values():
        stage_value(c, sector_betas[c["sector"]])
    valid = {t: c for t, c in valid.items() if c["gates"].passed and "dcf" in c}

    # ---- build-level gates
    problems = []
    share = len(valid) / len(C.UNIVERSE)
    if share < C.MIN_VALID_SHARE:
        problems.append(f"only {len(valid)}/{len(C.UNIVERSE)} companies passed their gates")
    for key, label in C.SECTORS.items():
        n = sum(1 for c in valid.values() if c["sector"] == key)
        if n < C.MIN_PER_SECTOR:
            problems.append(f"{label}: only {n} valid companies (need {C.MIN_PER_SECTOR})")
    invariants = [chk for c in valid.values() for chk in engine_invariants(c)]
    broken = [chk for chk in invariants if not chk["ok"]]
    for chk in broken:
        problems.append(f"engine invariant failed: {chk['ticker']} {chk['check']}")

    companies = []
    for c in valid.values():
        peers = [p for p in valid.values() if p["sector"] == c["sector"] and p["ticker"] != c["ticker"]]
        companies.append(company_payload(c, peers))

    presets = []
    for acq_t, tgt_t in C.MERGER_PRESETS:
        if acq_t in valid and tgt_t in valid:
            a = defaults.default_merger(merger_side(valid[acq_t]), merger_side(valid[tgt_t]), mkt)
            presets.append({"acquirer": acq_t, "target": tgt_t, "assumptions": a, "result": merger.run_merger(a)})

    def age_days(iso):
        return (now.date() - datetime.strptime(iso, "%Y-%m-%d").date()).days

    assumption_warnings = []
    if age_days(mkt["gsec_as_of"]) > C.ASSUMPTION_REVIEW_DAYS:
        assumption_warnings.append(f"G-sec yield last reviewed {mkt['gsec_as_of']} (over {C.ASSUMPTION_REVIEW_DAYS} days ago)")
    if age_days(mkt["erp_as_of"]) > C.ERP_REVIEW_DAYS:
        assumption_warnings.append(f"Equity risk premium last reviewed {mkt['erp_as_of']} (over {C.ERP_REVIEW_DAYS} days ago)")

    excluded = [{"ticker": t, "name": c["name"], "sector": c["sector"],
                 "reasons": [f"{f['id']}: {f['detail']}" for f in c["gates"].failed]}
                for t, c in staged.items() if t not in valid]

    data = {
        "schema_version": SCHEMA_VERSION,
        "meta": {
            "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "valuation_date": str(valuation_date.date()),
            "engine_version": ENGINE_VERSION,
            "currency": "INR",
            "units": "INR crore unless stated; per-share values in rupees; shares in crore",
            "source": "Yahoo Finance via yfinance (keyless), fetched server-side by a scheduled GitHub Action",
            "usdinr": usdinr_spot,
        },
        "market": dict(mkt, risk_free=mkt["gsec_10y"] - mkt["sovereign_spread"],
                       rating_table=[[None if math.isinf(lo) else lo, r, s] for lo, r, s in W.SYNTHETIC_RATING_TABLE]),
        "sectors": [{"key": k, "name": v, "unlevered_beta": sector_betas.get(k),
                     "tickers": [c["ticker"] for c in valid.values() if c["sector"] == k]}
                    for k, v in C.SECTORS.items()],
        "companies": companies,
        "merger_presets": presets,
        "quality": {
            "universe": len(C.UNIVERSE), "published": len(valid), "excluded": excluded,
            "assumption_warnings": assumption_warnings,
            "invariants_checked": len(invariants), "invariants_passed": len(invariants) - len(broken),
            "gates_checked": sum(len(c["gates"].results) for c in staged.values()),
            "gate_warnings": sum(len(c["gates"].warnings) for c in valid.values()),
        },
    }

    print(f"\n{len(valid)}/{len(C.UNIVERSE)} companies published, "
          f"{len(invariants) - len(broken)}/{len(invariants)} engine invariants hold")
    for e in excluded:
        print(f"  excluded {e['ticker']}: {'; '.join(e['reasons'])}")
    for w in assumption_warnings:
        print(f"  warning: {w}")
    if problems:
        print("\nBUILD FAILED, nothing written:")
        for p in problems:
            print(f"  - {p}")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = json.dumps(clean(data), separators=(",", ":"), allow_nan=False)
    with open(os.path.join(OUT_DIR, "deal-lab-data.json"), "w", encoding="utf-8") as fh:
        fh.write(payload + "\n")
    with open(os.path.join(OUT_DIR, "deal-lab-data.js"), "w", encoding="utf-8") as fh:
        fh.write("window.VDL_DATA = " + payload + ";\n")
    print(f"Wrote docs/data/deal-lab-data.json ({len(payload) / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
