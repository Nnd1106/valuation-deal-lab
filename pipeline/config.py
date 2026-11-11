"""config.py: the company universe and every market assumption, with sources.

Assumptions that cannot be fetched keylessly are fixed here with a source and
an as-of date. The build warns when a reviewed-by date is stale, and every
one of them can be overridden live in the interface.
"""

# ---------------------------------------------------------------- universe
# Non-financial Indian large caps in five peer groups. Banks, NBFCs and groups
# with a consolidated captive finance arm are excluded on purpose: free cash
# flow to the firm and EV multiples are not meaningful for them.
SECTORS = {
    "it": "IT Services",
    "fmcg": "Consumer Staples",
    "pharma": "Pharmaceuticals",
    "auto": "Automobiles",
    "cement": "Cement",
}

UNIVERSE = {
    "TCS": ("Tata Consultancy Services", "it"),
    "INFY": ("Infosys", "it"),
    "HCLTECH": ("HCL Technologies", "it"),
    "WIPRO": ("Wipro", "it"),
    "TECHM": ("Tech Mahindra", "it"),
    "HINDUNILVR": ("Hindustan Unilever", "fmcg"),
    "ITC": ("ITC", "fmcg"),
    "BRITANNIA": ("Britannia Industries", "fmcg"),
    "DABUR": ("Dabur India", "fmcg"),
    "MARICO": ("Marico", "fmcg"),
    "SUNPHARMA": ("Sun Pharmaceutical", "pharma"),
    "DRREDDY": ("Dr. Reddy's Laboratories", "pharma"),
    "CIPLA": ("Cipla", "pharma"),
    "LUPIN": ("Lupin", "pharma"),
    "ZYDUSLIFE": ("Zydus Lifesciences", "pharma"),
    "MARUTI": ("Maruti Suzuki India", "auto"),
    "BAJAJ-AUTO": ("Bajaj Auto", "auto"),
    "EICHERMOT": ("Eicher Motors", "auto"),
    "HEROMOTOCO": ("Hero MotoCorp", "auto"),
    "ULTRACEMCO": ("UltraTech Cement", "cement"),
    "SHREECEM": ("Shree Cement", "cement"),
    "AMBUJACEM": ("Ambuja Cements", "cement"),
    "DALBHARAT": ("Dalmia Bharat", "cement"),
    "JKCEMENT": ("JK Cement", "cement"),
}

EXCHANGE_SUFFIX = ".NS"
MARKET_INDEX = "^NSEI"
USDINR = "USDINR=X"

# Illustrative same-sector pairs for the M&A module. They are examples for
# the mechanics only and do not suggest that any transaction is contemplated.
MERGER_PRESETS = [
    ("ULTRACEMCO", "JKCEMENT"),
    ("HINDUNILVR", "DABUR"),
    ("SUNPHARMA", "LUPIN"),
    ("TCS", "TECHM"),
    ("BAJAJ-AUTO", "HEROMOTOCO"),
]

# ---------------------------------------------------------------- market assumptions
MARKET = {
    # India 10-year government bond yield.
    "gsec_10y": 0.0712,
    "gsec_as_of": "2026-11-06",
    "gsec_source": "India 10-year G-sec benchmark yield (Trading Economics, 6 Nov 2026)",

    # Country risk, A. Damodaran, "Country Default Spreads and Risk Premiums".
    # India is rated Baa3: rating-based default spread 1.87%, total equity
    # risk premium 7.08% (mature-market premium 4.23% + country premium 2.85%).
    "sovereign_spread": 0.0187,
    "erp": 0.0708,
    "erp_as_of": "2026-01-05",
    "erp_source": "Damodaran country risk premiums, 5 Jan 2026 (India, Moody's Baa3)",

    # Synthetic rating spreads live in engine/wacc.py (Damodaran, Jan 2026).
    "rating_source": "Damodaran ratings, interest coverage and default spreads, Jan 2026",

    # Corporate tax under section 115BAA: 22% x 1.10 surcharge x 1.04 cess.
    "tax_rate": 0.2517,
    "tax_source": "Income-tax Act s.115BAA: 22% + 10% surcharge + 4% cess = 25.17%",

    # Long-run nominal growth cap; never allowed above the risk-free rate.
    "terminal_growth": 0.05,

    # Pre-tax yield assumed on balance-sheet cash used in an acquisition.
    "cash_yield": 0.065,

    # Illustrative take-private terms.
    "lbo_premium": 0.25,
    "lbo_fee_pct": 0.02,
    "lbo_senior_x": 3.0,
    "lbo_senior_spread": 0.030,
    "lbo_senior_amort_pct": 0.05,
    "lbo_sub_x": 1.5,
    "lbo_sub_spread": 0.055,

    # Illustrative acquisition terms.
    "ma_premium": 0.25,
    "ma_synergy_pct_revenue": 0.02,
    "ma_fee_pct": 0.01,
    "ma_intangibles_pct": 0.25,
    "ma_amort_years": 10,
}

ASSUMPTION_REVIEW_DAYS = 45      # warn when the G-sec yield is older than this
ERP_REVIEW_DAYS = 400            # the country risk table is updated twice a year

# ---------------------------------------------------------------- data rules
BETA_WINDOW_WEEKS = 260          # five years of weekly returns
BETA_MIN_WEEKS = 104
PRICE_HISTORY_YEARS = 6
FUNDAMENTALS_MAX_AGE_DAYS = 7    # re-fetch statements weekly
MIN_FISCAL_YEARS = 3
MIN_VALID_SHARE = 0.75           # build fails below this share of the universe
MIN_PER_SECTOR = 3               # build fails if a peer group gets thinner

SENS_WACC_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)
SENS_GROWTH_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)
LBO_TARGET_IRRS = (0.25, 0.15)   # football-field band: price a sponsor can pay
