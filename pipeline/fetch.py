"""fetch.py: keyless market data via yfinance.

Two kinds of data with different lifetimes:
  - fundamentals (statements) change quarterly, so they are snapshotted to
    data/fundamentals/<TICKER>.json and refreshed weekly;
  - prices are fetched on every run and never stored outside the published
    data file.
"""

from __future__ import annotations

import json
import math
import os
import time
import warnings
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

import config as C

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(ROOT, "data", "fundamentals")

INFO_KEYS = ("longName", "sector", "industry", "currency", "financialCurrency",
             "sharesOutstanding", "trailingEps", "currentPrice", "previousClose")
NSE_SETTLED = (16, 0)   # 15:30 IST close plus a settle buffer


def _frame_to_dict(df) -> dict:
    if df is None or df.empty:
        return {}
    out = {}
    for col in df.columns:
        period = str(pd.Timestamp(col).date())
        out[period] = {str(k): float(v) for k, v in df[col].items() if not pd.isna(v)}
    return out


def fetch_fundamentals(ticker: str, retries: int = 3) -> dict | None:
    """Raw annual and quarterly statements plus a small set of quote fields."""
    symbol = ticker + C.EXCHANGE_SUFFIX
    for attempt in range(retries):
        try:
            t = yf.Ticker(symbol)
            raw = {
                "ticker": ticker,
                "symbol": symbol,
                "fetched_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "income": _frame_to_dict(t.income_stmt),
                "balance": _frame_to_dict(t.balance_sheet),
                "cashflow": _frame_to_dict(t.cashflow),
                "q_income": _frame_to_dict(t.quarterly_income_stmt),
                "q_balance": _frame_to_dict(t.quarterly_balance_sheet),
            }
            info = t.info or {}
            raw["info"] = {k: info.get(k) for k in INFO_KEYS}
            if raw["income"] and raw["balance"] and raw["cashflow"]:
                return raw
            print(f"  ! {ticker}: empty statements (attempt {attempt + 1})")
        except Exception as exc:
            print(f"  ! {ticker} fundamentals attempt {attempt + 1} failed: {exc}")
        time.sleep(2.0 * (attempt + 1))
    return None


def snapshot_path(ticker: str) -> str:
    return os.path.join(SNAPSHOT_DIR, f"{ticker}.json")


def load_snapshot(ticker: str) -> dict | None:
    path = snapshot_path(ticker)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(raw: dict) -> None:
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    with open(snapshot_path(raw["ticker"]), "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=1, sort_keys=True)
        fh.write("\n")


def snapshot_age_days(raw: dict | None) -> float:
    if not raw or not raw.get("fetched_utc"):
        return math.inf
    fetched = datetime.strptime(raw["fetched_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched).total_seconds() / 86400.0


def _drop_unfinished_session(df: pd.DataFrame) -> pd.DataFrame:
    """Drop today's bar while the NSE session is still open, so an intraday
    price is never recorded as a close."""
    idx = pd.to_datetime(df.index)
    if len(idx) == 0 or idx.tz is None:
        return df
    now = pd.Timestamp.now(tz=idx.tz)
    if idx[-1].date() != now.date():
        return df
    hh, mm = NSE_SETTLED if str(idx.tz) == "Asia/Kolkata" else (23, 59)
    if now < now.normalize() + pd.Timedelta(hours=hh, minutes=mm):
        return df.iloc[:-1]
    return df


def fetch_history(symbol: str, years: int = C.PRICE_HISTORY_YEARS, retries: int = 3) -> pd.DataFrame:
    """Daily history with a tz-naive index (empty on failure).

    Close      traded price (split-adjusted only): quotes and 52-week range
    AdjClose   dividend- and split-adjusted: total returns for beta
    Dividends  cash dividend per share on its ex-date
    """
    for attempt in range(retries):
        try:
            raw = yf.Ticker(symbol).history(period=f"{years}y", auto_adjust=False)
            if raw is not None and not raw.empty:
                df = _drop_unfinished_session(raw)
                out = pd.DataFrame({
                    "Close": df["Close"],
                    "AdjClose": df["Adj Close"] if "Adj Close" in df else df["Close"],
                    "Dividends": df["Dividends"] if "Dividends" in df else 0.0,
                })
                out.index = pd.to_datetime(out.index).tz_localize(None).normalize()
                out = out[~out.index.duplicated(keep="last")].sort_index()
                return out[(out["Close"] > 0) & (out["AdjClose"] > 0)]
        except Exception as exc:
            print(f"  ! {symbol} history attempt {attempt + 1} failed: {exc}")
        time.sleep(1.5 * (attempt + 1))
    return pd.DataFrame(columns=["Close", "AdjClose", "Dividends"])
