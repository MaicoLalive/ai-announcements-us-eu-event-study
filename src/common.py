"""Paths, data loaders and test statistics shared by the notebooks."""

import os
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats as st
from linearmodels import PanelOLS

pd.set_option("display.precision", 4)   # tables are stored at full precision

# ---------------------------------------------------------------- paths
REPO = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("DATA_DIR", REPO / "data"))
OUTPUT = Path(os.environ.get("OUTPUT_DIR", REPO / "output"))
TABLES = OUTPUT / "tables"
INTERIM = OUTPUT / "intermediate"
LATEX = OUTPUT / "latex"
FIGURES = REPO / "figures"
for _p in (TABLES, INTERIM, LATEX, FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- inputs
# Location of each input relative to DATA_DIR; adjust to match your copies.
# data/README.md describes what each input must contain.
INPUTS = {
    "events": "events.xlsx",
    "us_constituents": "wrds/US_SP500_constituents.parquet",
    "us_returns": "wrds/US_daily_returns_marketcap.parquet",
    "eu_constituents": "wrds/EU_STOXX600_constituents.parquet",
    "eu_returns": "wrds/EU_daily_returns_marketcap.parquet",
    "earnings_us": "wrds/ibes_earnings_us.parquet",
    "earnings_intl": "wrds/ibes_earnings_intl.parquet",
    "accounting_us": "wrds/comp_firm_chars.parquet",
    "accounting_global": "wrds/comp_global_chars.parquet",
    "factors_us": "french/F-F_Research_Data_5_Factors_2x3_daily.csv",
    "factors_eu": "french/Europe_5_Factors_Daily.csv",
}
# Fields of the event list.
EVENT_COLUMNS = ["Company", "Ticker", "Date", "Region", "Event_Type", "Description", "Record_Firms",
                 "Firm_Hosted", "IBES_Name", "Verified_Results_Date", "Datastream_Ticker"]


def input_path(name):
    return DATA / INPUTS[name]

# ---------------------------------------------------------------- design
EST_LEN, EST_GAP, MIN_OBS = 250, 20, 120   # estimation window tau = -250, ..., -20
FCOLS = ["MKT", "SMB", "HML", "RMW", "CMA"]
K_VALS = list(range(-5, 6))
WINDOWS = [("[-1,+1]", -1, 1), ("[0,+1]", 0, 1), ("[0,+3]", 0, 3), ("[-2,+2]", -2, 2),
           ("[-3,+3]", -3, 3), ("[-4,+4]", -4, 4), ("[-5,+5]", -5, 5)]


def ar_col(k):
    return f"AR_k{'+' if k >= 0 else ''}{k}"


def date_col(k):
    return f"Date_k{'+' if k >= 0 else ''}{k}"


def lev_col(k1, k2):
    return f"Lev_k{k1:+d}_{k2:+d}"


def window_cols(k1, k2):
    return [ar_col(k) for k in range(k1, k2 + 1)]


ARC = [ar_col(k) for k in K_VALS]
DATEC = [date_col(k) for k in K_VALS]

GICS_TO_BROAD = {
    "10": "Energy", "15": "Industrials", "20": "Industrials", "25": "Consumer",
    "30": "Consumer", "35": "Healthcare", "40": "Financials", "45": "Technology",
    "50": "Communications", "55": "Utilities", "60": "Financials",
}


def star(p):
    if pd.isna(p):
        return ""
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""


def p_two_sided(t, df):
    return 2 * (1 - st.t.cdf(abs(t), df=df))


# ---------------------------------------------------------------- data
def load_constituents():
    us = pd.read_parquet(input_path("us_constituents"))
    eu = pd.read_parquet(input_path("eu_constituents"))
    return us, eu


def load_returns():
    """Daily returns and market caps. EU values are in USD."""
    us = pd.read_parquet(input_path("us_returns"))
    eu = pd.read_parquet(input_path("eu_returns"))
    us["date"] = pd.to_datetime(us["date"])
    eu["date"] = pd.to_datetime(eu["date"])
    assert eu["ret_usd"].isna().mean() < 0.02, "EU ret_usd coverage below 98%"
    return us, eu


def series_by_id(df, key, col):
    out = {}
    for k, g in df[[key, "date", col]].dropna().groupby(key):
        s = pd.Series(g[col].values, index=g["date"].values)
        out[k] = s[~s.index.duplicated(keep="last")].sort_index()
    return out


def return_series():
    """{"US": {permno: returns}, "EU": {infocode: returns}}."""
    us, eu = load_returns()
    return {"US": series_by_id(us, "permno", "daily_return"),
            "EU": series_by_id(eu, "infocode", "ret_usd")}


def load_ff(region):
    ff = pd.read_csv(input_path({"US": "factors_us", "EU": "factors_eu"}[region]), skiprows=3)
    ff.columns = ["date", "MKT", "SMB", "HML", "RMW", "CMA", "RF"]
    ff = ff[pd.to_numeric(ff["date"], errors="coerce").notna()]
    ff["date"] = pd.to_datetime(ff["date"].astype(int).astype(str))
    for c in ff.columns[1:]:
        ff[c] = ff[c].astype(float) / 100
    return ff.set_index("date")


def load_factors():
    return {"US": load_ff("US"), "EU": load_ff("EU")}


def load_sample():
    """The final event sample built by notebook 01."""
    return pd.read_parquet(INTERIM / "events_final.parquet")


# ---------------------------------------------------------------- linking
def constituent_maps(us_c, eu_c):
    """Ticker -> identifier maps. Tickers with more than one identifier are kept apart."""
    def build(c, key):
        pairs = c[[key, "ticker"]].dropna().drop_duplicates()
        counts = pairs.groupby("ticker")[key].nunique()
        ok = set(counts[counts == 1].index)
        clean = {t: i for t, i in zip(pairs["ticker"], pairs[key]) if t in ok}
        amb = {t: sorted(pairs.loc[pairs["ticker"] == t, key].unique().tolist())
               for t in counts[counts > 1].index}
        return clean, amb

    us_map, us_amb = build(us_c, "permno")
    eu_map, eu_amb = build(eu_c, "infocode")
    ambiguous = {**{("US", t): v for t, v in us_amb.items()},
                 **{("EU", t): v for t, v in eu_amb.items()}}
    return us_map, eu_map, ambiguous


def resolve_identifier(ticker, region, ds_ticker, us_map, eu_map, ambiguous):
    """Bloomberg ticker + region -> (permno or infocode, region). Same-region matches only.
    ds_ticker is the Datastream ticker where its convention differs from Bloomberg's."""
    base = ticker.split()[0]
    alt = ds_ticker if isinstance(ds_ticker, str) and ds_ticker else base
    cands = []
    for b in {base, alt}:
        if (region, b) in ambiguous:
            raise ValueError(f"Ambiguous {region} ticker {b!r}: {ambiguous[(region, b)]}")
        if b in us_map:
            cands.append((us_map[b], "US"))
        if b in eu_map:
            cands.append((eu_map[b], "EU"))
    same = sorted({c for c in cands if c[1] == region})
    if len(same) > 1:
        raise ValueError(f"{ticker!r} resolves to several {region} identifiers: {same}")
    return same[0] if same else (None, None)


# ---------------------------------------------------------------- CAAR tests
def kp_factor(z, rho, n):
    """Kolari-Pynnonen factor scaled by the number of ordered same-date pairs
    S = sum_d n_d (n_d - 1):  sqrt([1 - rho S / (N(N-1))] / [1 + rho S / N]).
    Equals the original KP factor when all events share one date and 1 when no two do."""
    nd = z.groupby("Date").size().to_numpy()
    pairs = float((nd * (nd - 1)).sum())
    if not n or n < 2:
        return np.nan, pairs
    numer = 1 - rho * pairs / (n * (n - 1))
    denom = 1 + rho * pairs / n
    factor = np.sqrt(numer / denom) if (numer > 0 and denom > 0) else np.nan
    return factor, pairs


def caar_stats(sub, k1, k2, rho=None, wcol="MktCap_USDm"):
    """EW CAAR with the BMP test (forecast-error term included), VW CAAR with the
    Kish effective N, and the KP-corrected test when rho is given."""
    ks = window_cols(k1, k2)
    levc = lev_col(k1, k2)
    z = sub.dropna(subset=ks + ["Sigma", levc])
    z = z[z["Sigma"] > 0]
    car = z[ks].sum(axis=1)
    n = len(z)
    if n < 3:
        return dict(N=n)
    sar = car / (z["Sigma"] * 100 * np.sqrt(len(ks) + z[levc]))
    t_ew = sar.mean() / (sar.std(ddof=1) / np.sqrt(n)) if sar.std(ddof=1) > 0 else np.nan
    out = dict(N=n, EW_CAAR=car.mean(), t_EW=t_ew,
               p_EW=p_two_sided(t_ew, n - 1))
    if wcol in z.columns and z[wcol].notna().all():
        w = z[wcol].to_numpy(float)
        w = w / w.sum()
        vw = float((car.to_numpy() * w).sum())
        eff = 1.0 / np.sum(w ** 2)
        wvar = float((w * (car.to_numpy() - vw) ** 2).sum()) * (eff / (eff - 1))
        t_vw = vw / np.sqrt(wvar / eff) if wvar > 0 else np.nan
        out.update(VW_CAAR=vw, t_VW=t_vw,
                   p_VW=p_two_sided(t_vw, max(int(round(eff)) - 1, 1)),
                   eff_N=eff)
    if rho is not None:
        factor, pairs = kp_factor(z, rho, n)
        if rho > 0 and np.isfinite(factor):
            t_kp, used = t_ew * factor, "KP"
        else:
            t_kp, used = t_ew, "BMP"
        out.update(rho_bar=rho, same_date_pairs=int(pairs),
                   t_used=t_kp, p_used=p_two_sided(t_kp, n - 1), stat=used)
    return out


class ResidualCorrelation:
    """Average cross-correlation of estimation-window residuals (rho_bar for KP).

    Estimated on the group's same-date event pairs; with fewer than 10 usable
    pairs it falls back to random pairs from the whole group."""

    MIN_OVERLAP = 30
    MIN_SD_PAIRS = 10

    def __init__(self, path=INTERIM / "estimation_residuals.parquet"):
        panel = pd.read_parquet(path)
        self.resid = {(t, d): g.set_index("est_date")["resid"]
                      for (t, d), g in panel.groupby(["Ticker", "Date"])}

    def _corr(self, keys, pairs):
        out = []
        for i, j in pairs:
            si, sj = self.resid[keys[i]], self.resid[keys[j]]
            common = si.index.intersection(sj.index)
            if len(common) < self.MIN_OVERLAP:
                continue
            xi, xj = si.loc[common].to_numpy(), sj.loc[common].to_numpy()
            if xi.std() == 0 or xj.std() == 0:
                continue
            out.append(float(np.corrcoef(xi, xj)[0, 1]))
        return out

    def rho_bar(self, sub):
        keys = [(t, d) for t, d in zip(sub["Ticker"], sub["Date"]) if (t, d) in self.resid]
        n = len(keys)
        if n < 3:
            return 0.0
        rng = np.random.default_rng(42)
        by_date = {}
        for i, (_, d) in enumerate(keys):
            by_date.setdefault(d, []).append(i)
        sd_pairs = [p for idx in by_date.values() if len(idx) > 1 for p in combinations(idx, 2)]
        if len(sd_pairs) > 3000:
            pick = rng.choice(len(sd_pairs), size=3000, replace=False)
            sd_pairs = [sd_pairs[int(i)] for i in pick]
        rhos = self._corr(keys, sd_pairs)
        if len(rhos) >= self.MIN_SD_PAIRS:
            return float(np.mean(rhos))
        if n <= 64:
            rn_pairs = list(combinations(range(n), 2))
        else:
            raw = rng.choice(n, size=(6000, 2), replace=True)
            rn_pairs = [(int(a), int(b)) for a, b in raw if a != b][:2000]
        rhos = self._corr(keys, rn_pairs)
        return float(np.mean(rhos)) if rhos else 0.0


# ---------------------------------------------------------------- regressions
def clustered_ols(y, X, entity, time, firm, date):
    """OLS with standard errors clustered by firm and calendar date."""
    idx = pd.MultiIndex.from_arrays([entity, time], names=["entity", "time"])
    clusters = pd.DataFrame({"firm": np.asarray(firm), "date": np.asarray(date)}, index=idx)
    return PanelOLS(y.set_axis(idx), X.set_axis(idx), entity_effects=False,
                    time_effects=False).fit(cov_type="clustered", clusters=clusters)


def coef_table(res, **extra):
    return pd.DataFrame([dict(**extra, variable=v, coef=float(res.params[v]),
                              se=float(res.std_errors[v]),
                              t=float(res.tstats[v]),
                              p=float(res.pvalues[v]),
                              sig=star(float(res.pvalues[v])), N=int(res.nobs))
                         for v in res.params.index])
