"""
Clinical Trial CDM Quality System
=================================

A Streamlit dashboard for Clinical Data Management (CDM) monitoring:
data overview -> validation findings -> query management -> site performance
-> database-lock readiness, plus an interactive 3D lab.

Run
---
    pip install -r requirements.txt
    streamlit run app.py

Expected folder layout (next to this file)::

    01_Data/
        cleaned/            sites.csv, subjects.csv, visits.csv, lab_results.csv,
                            vital_signs.csv, adverse_events.csv,
                            concomitant_medications.csv, protocol_deviations.csv
        validation_output/  data_quality_results.csv, queries.csv, kpi_summary.csv,
                            site_performance.csv, database_lock_readiness.csv,
                            validation_rule_catalog.csv

If the CSV files are missing, the app falls back to a built-in synthetic demo
dataset, so every page always renders.
"""

from __future__ import annotations

import html
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

# ============================================================
# PAGE CONFIG (must be the first Streamlit call)
# ============================================================

APP_TITLE = "Clinical Trial CDM Quality System"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

LOGGER = logging.getLogger("cdm_quality_system")

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "01_Data"
CLEANED_DIR = DATA_DIR / "cleaned"
OUTPUT_DIR = DATA_DIR / "validation_output"

# dataset key -> (folder, filename, display label)
DATASET_REGISTRY: dict[str, tuple[Path, str, str]] = {
    "sites": (CLEANED_DIR, "sites.csv", "Sites"),
    "subjects": (CLEANED_DIR, "subjects.csv", "Subjects"),
    "visits": (CLEANED_DIR, "visits.csv", "Visits"),
    "labs": (CLEANED_DIR, "lab_results.csv", "Lab Results"),
    "vitals": (CLEANED_DIR, "vital_signs.csv", "Vital Signs"),
    "aes": (CLEANED_DIR, "adverse_events.csv", "Adverse Events"),
    "conmeds": (CLEANED_DIR, "concomitant_medications.csv", "Concomitant Medications"),
    "deviations": (CLEANED_DIR, "protocol_deviations.csv", "Protocol Deviations"),
    "quality": (OUTPUT_DIR, "data_quality_results.csv", "Data Quality Results"),
    "queries": (OUTPUT_DIR, "queries.csv", "Queries"),
    "kpi": (OUTPUT_DIR, "kpi_summary.csv", "KPI Summary"),
    "site_perf": (OUTPUT_DIR, "site_performance.csv", "Site Performance"),
    "lock": (OUTPUT_DIR, "database_lock_readiness.csv", "Database Lock Readiness"),
    "rules": (OUTPUT_DIR, "validation_rule_catalog.csv", "Validation Rule Catalog"),
}

CLINICAL_KEYS = ("sites", "subjects", "visits", "labs", "vitals", "aes", "conmeds", "deviations")
EXPLORER_KEYS = CLINICAL_KEYS + ("quality", "queries", "site_perf")
SITE_FILTERABLE_KEYS = CLINICAL_KEYS + ("quality", "queries", "site_perf")

ACTIVE_QUERY_STATUSES = frozenset({"OPEN", "UNDER_REVIEW", "SENT_TO_SITE", "SITE_RESPONDED", "REOPENED"})
CLOSED_QUERY_STATUSES = frozenset({"CLOSED", "RESOLVED"})
OVERDUE_BUCKETS = frozenset({"OVERDUE", "CRITICAL"})
RESOLVED_ISSUE_STATUSES = frozenset({"CLOSED", "RESOLVED", "FIXED", "COMPLETE", "COMPLETED"})

STATUS_ORDER = ("OPEN", "UNDER_REVIEW", "SENT_TO_SITE", "SITE_RESPONDED", "REOPENED", "RESOLVED", "CLOSED")
PRIORITY_ORDER = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
AGING_ORDER = ("0-7 DAYS", "8-14 DAYS", "15-30 DAYS", "OVERDUE", "CRITICAL")
SEVERITY_ORDER = ("CRITICAL", "MAJOR", "MINOR")

QUERY_DATE_COLUMNS = (
    "CREATED_DATE", "QUERY_DATE", "OPEN_DATE", "RAISED_DATE",
    "CREATED_ON", "QUERY_CREATED_DATE", "DATE_RAISED",
)
DEVIATION_CATEGORY_COLUMNS = ("CATEGORY", "DEVIATION_CATEGORY", "DEVIATION_TYPE", "TYPE")
QUALITY_DATASET_COLUMNS = ("DATASET", "TABLE_NAME", "TABLE", "DOMAIN")

CLOSURE_RATE_TARGET = 95.0

COLORS = {
    "primary": "#38bdf8",
    "accent": "#a78bfa",
    "success": "#34d399",
    "warning": "#fbbf24",
    "danger": "#f87171",
    "orange": "#fb923c",
    "muted": "#94a3b8",
    "text": "#e2e8f0",
}
PALETTE = ["#38bdf8", "#a78bfa", "#34d399", "#fbbf24", "#f87171", "#fb923c", "#f472b6", "#2dd4bf"]
SEVERITY_COLORS = {
    "CRITICAL": COLORS["danger"],
    "MAJOR": COLORS["orange"],
    "MINOR": COLORS["warning"],
}
PRIORITY_COLORS = {
    "CRITICAL": COLORS["danger"],
    "HIGH": COLORS["orange"],
    "MEDIUM": COLORS["warning"],
    "LOW": COLORS["success"],
}

# Streamlit renamed `use_container_width` to `width="stretch"` in 1.50.
try:
    _ST_VERSION = tuple(int(p) for p in st.__version__.split(".")[:2])
except ValueError:  # pragma: no cover - defensive
    _ST_VERSION = (0, 0)
STRETCH: dict[str, Any] = {"width": "stretch"} if _ST_VERSION >= (1, 50) else {"use_container_width": True}


# ============================================================
# SMALL UTILITIES
# ============================================================

def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert to a finite float, falling back to ``default``."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(number) or math.isinf(number) else number


def fmt_int(value: Any) -> str:
    """Thousands-separated integer string; never raises."""
    return f"{int(round(safe_float(value))):,}"


def col_upper(df: pd.DataFrame, column: str) -> pd.Series:
    """Upper-cased, stripped string view of a column.

    Returns a same-index series of empty strings when the column is missing,
    so boolean masks built from different columns always align.
    """
    if column not in df.columns:
        return pd.Series("", index=df.index, dtype=object)
    return df[column].fillna("").astype(str).str.strip().str.upper()


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    """First candidate column present in ``df`` (or ``None``)."""
    return next((c for c in candidates if c in df.columns), None)


def numeric(df: pd.DataFrame, column: str) -> pd.Series:
    """Numeric view of a column (NaN where not parseable / missing)."""
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def ordered(values: Iterable[str], canonical: Sequence[str]) -> list[str]:
    """Order ``values`` by a canonical list first, then alphabetically."""
    present = {v for v in values if v}
    return [v for v in canonical if v in present] + sorted(present - set(canonical))


def count_frame(series: pd.Series, label: str, canonical: Sequence[str] = ()) -> pd.DataFrame:
    """Value counts as a tidy two-column frame (label, COUNT)."""
    clean = series[series != ""]
    if clean.empty:
        return pd.DataFrame({label: [], "COUNT": []})
    counts = clean.value_counts()
    order = ordered(counts.index, canonical)
    return pd.DataFrame({label: order, "COUNT": [int(counts[k]) for k in order]})


# ============================================================
# DATA LAYER
# ============================================================

@dataclass
class DataBundle:
    """All datasets plus diagnostics about how they were loaded."""

    frames: dict[str, pd.DataFrame]
    is_demo: bool = False
    messages: list[tuple[str, str]] = field(default_factory=list)  # (level, text)

    def __getitem__(self, key: str) -> pd.DataFrame:
        return self.frames.get(key, pd.DataFrame())


@st.cache_data(show_spinner=False)
def _read_csv_cached(path_str: str, mtime: float) -> tuple[pd.DataFrame, str | None]:
    """Read one CSV. ``mtime`` is part of the cache key so edits are picked up."""
    try:
        df = pd.read_csv(path_str, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(), None  # zero-byte / header-less file: treated as empty, not an error
    except Exception as exc:  # noqa: BLE001 - surface any parse problem to the UI
        return pd.DataFrame(), str(exc)
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df, None


@st.cache_data(show_spinner=False)
def build_demo_data(seed: int = 42) -> dict[str, pd.DataFrame]:
    """Synthetic, internally consistent CDM dataset used when CSVs are absent."""
    rng = np.random.default_rng(seed)
    n_sites, n_subjects = 24, 480
    site_ids = [f"SITE-{i:03d}" for i in range(1, n_sites + 1)]
    countries = ["India", "USA", "Germany", "UK", "Japan", "Brazil", "France", "Canada"]
    anchor = pd.Timestamp.today().normalize()

    sites = pd.DataFrame({
        "SITE_ID": site_ids,
        "SITE_NAME": [f"Clinical Site {i}" for i in range(1, n_sites + 1)],
        "COUNTRY": rng.choice(countries, n_sites),
        "STATUS": rng.choice(["ACTIVE", "ACTIVE", "ACTIVE", "CLOSED"], n_sites),
    })

    site_weights = rng.dirichlet(np.linspace(1.5, 0.6, n_sites))
    subj_site = rng.choice(site_ids, n_subjects, p=site_weights)
    subjects = pd.DataFrame({
        "SUBJECT_ID": [f"SUBJ-{i:04d}" for i in range(1, n_subjects + 1)],
        "SITE_ID": subj_site,
        "AGE": rng.integers(18, 80, n_subjects),
        "SEX": rng.choice(["M", "F"], n_subjects),
        "ARM": rng.choice(["PLACEBO", "DRUG_A", "DRUG_B"], n_subjects),
        "ENROLL_DATE": anchor - pd.to_timedelta(rng.integers(30, 330, n_subjects), unit="D"),
    })

    n_visits = rng.integers(3, 6, n_subjects)
    visit_num = np.concatenate([np.arange(1, c + 1) for c in n_visits])
    enroll = np.repeat(subjects["ENROLL_DATE"].to_numpy(), n_visits)
    visits = pd.DataFrame({
        "VISIT_ID": [f"V{i:05d}" for i in range(1, len(visit_num) + 1)],
        "SUBJECT_ID": np.repeat(subjects["SUBJECT_ID"].to_numpy(), n_visits),
        "SITE_ID": np.repeat(subjects["SITE_ID"].to_numpy(), n_visits),
        "VISIT_NUM": visit_num,
        "VISIT_DATE": pd.to_datetime(enroll) + pd.to_timedelta(visit_num * 28, unit="D"),
    })

    def pick(n: int) -> pd.DataFrame:
        return visits.iloc[rng.integers(0, len(visits), n)][["SUBJECT_ID", "SITE_ID", "VISIT_DATE"]].reset_index(drop=True)

    labs = pick(1800)
    labs.insert(0, "LAB_ID", [f"L{i:05d}" for i in range(1, 1801)])
    labs["TEST"] = rng.choice(["ALT", "AST", "HGB", "CREAT"], 1800)
    labs["VALUE"] = np.round(rng.normal(50, 15, 1800), 2)

    vitals = pick(1500)
    vitals.insert(0, "VITAL_ID", [f"VS{i:05d}" for i in range(1, 1501)])
    vitals["SYSBP"] = np.round(rng.normal(125, 15, 1500), 0)
    vitals["DIABP"] = np.round(rng.normal(80, 9, 1500), 0)
    vitals["HEART_RATE"] = np.round(rng.normal(74, 10, 1500), 0)

    aes = pick(260)
    aes.insert(0, "AE_ID", [f"AE{i:04d}" for i in range(1, 261)])
    aes["AE_TERM"] = rng.choice(["Headache", "Nausea", "Fatigue", "Rash", "Dizziness", "Pyrexia"], 260)
    aes["SEVERITY"] = rng.choice(["MILD", "MODERATE", "SEVERE"], 260, p=[0.55, 0.35, 0.10])
    aes["SERIOUS"] = rng.choice(["Y", "N"], 260, p=[0.08, 0.92])

    conmeds = pick(400)
    conmeds.insert(0, "CM_ID", [f"CM{i:04d}" for i in range(1, 401)])
    conmeds["MEDICATION"] = rng.choice(["Paracetamol", "Metformin", "Atorvastatin", "Amlodipine", "Omeprazole"], 400)

    deviations = pick(150)
    deviations.insert(0, "DEVIATION_ID", [f"PD{i:04d}" for i in range(1, 151)])
    deviations["CATEGORY"] = rng.choice(
        ["Visit window", "Informed consent", "Dosing", "Eligibility", "Missed assessment"], 150)

    # --- validation outputs -------------------------------------------------
    n_issues = 520
    quality = pd.DataFrame({
        "ISSUE_ID": [f"DQ{i:04d}" for i in range(1, n_issues + 1)],
        "RULE_ID": [f"R{i:03d}" for i in rng.integers(1, 41, n_issues)],
        "DATASET": rng.choice(["Subjects", "Visits", "Lab Results", "Vital Signs", "Adverse Events"], n_issues),
        "SITE_ID": rng.choice(site_ids, n_issues, p=site_weights),
        "SEVERITY": rng.choice(list(SEVERITY_ORDER), n_issues, p=[0.07, 0.31, 0.62]),
        "STATUS": rng.choice(["OPEN", "OPEN", "RESOLVED"], n_issues),
    })

    n_queries = 640
    age_days = np.minimum(rng.exponential(30, n_queries).astype(int), 240)
    status = rng.choice(list(STATUS_ORDER), n_queries, p=[0.17, 0.10, 0.09, 0.08, 0.04, 0.22, 0.30])
    aging = np.select(
        [age_days <= 7, age_days <= 14, age_days <= 30, age_days <= 60],
        ["0-7 Days", "8-14 Days", "15-30 Days", "Overdue"],
        default="Critical",
    )
    queries = pd.DataFrame({
        "QUERY_ID": [f"Q{i:05d}" for i in range(1, n_queries + 1)],
        "SITE_ID": rng.choice(site_ids, n_queries, p=site_weights),
        "PRIORITY": rng.choice(list(PRIORITY_ORDER), n_queries, p=[0.07, 0.23, 0.45, 0.25]),
        "QUERY_STATUS": status,
        "AGING_BUCKET": aging,
        "AGE_DAYS": age_days,
        "CREATED_DATE": anchor - pd.to_timedelta(age_days, unit="D"),
    })

    def per_site(frame: pd.DataFrame) -> pd.Series:
        return sites["SITE_ID"].map(frame["SITE_ID"].value_counts()).fillna(0).astype(int)

    closed = queries[queries["QUERY_STATUS"].isin(CLOSED_QUERY_STATUSES)]
    site_perf = pd.DataFrame({"SITE_ID": site_ids})
    site_perf["SUBJECTS"] = per_site(subjects)
    site_perf["DEVIATIONS"] = per_site(deviations)
    site_perf["QUERIES"] = per_site(queries)
    site_perf["QUERY_RESOLUTION_RATE_PCT"] = (
        (per_site(closed) / site_perf["QUERIES"].clip(lower=1) * 100).round(1)
    )
    issues_per_subject = per_site(quality) / site_perf["SUBJECTS"].clip(lower=1)
    site_perf["QUALITY_SCORE"] = (
        96 - 14 * issues_per_subject - 0.12 * (100 - site_perf["QUERY_RESOLUTION_RATE_PCT"])
        + rng.normal(0, 2.0, n_sites)
    ).clip(35, 99).round(1)

    lock = pd.DataFrame({
        "CRITERION": ["Critical discrepancies", "Critical queries", "SAE reconciliation", "Coding complete"],
        "STATUS": ["BLOCKING", "BLOCKING", "PENDING", "COMPLETE"],
        "DETAIL": ["Critical findings open", "Critical-priority queries active",
                   "Awaiting safety DB match", "MedDRA / WHODrug coded"],
    })
    rules = pd.DataFrame({
        "RULE_ID": [f"R{i:03d}" for i in range(1, 41)],
        "DATASET": rng.choice(["Subjects", "Visits", "Lab Results", "Vital Signs", "Adverse Events"], 40),
        "SEVERITY": rng.choice(list(SEVERITY_ORDER), 40, p=[0.15, 0.35, 0.50]),
        "DESCRIPTION": [f"Validation check #{i}" for i in range(1, 41)],
    })
    kpi = pd.DataFrame({
        "METRIC": ["Subjects enrolled", "Open queries", "Critical findings"],
        "VALUE": [n_subjects, int((~queries["QUERY_STATUS"].isin(CLOSED_QUERY_STATUSES)).sum()),
                  int((quality["SEVERITY"] == "CRITICAL").sum())],
    })

    frames = {
        "sites": sites, "subjects": subjects, "visits": visits, "labs": labs, "vitals": vitals,
        "aes": aes, "conmeds": conmeds, "deviations": deviations, "quality": quality,
        "queries": queries, "kpi": kpi, "site_perf": site_perf, "lock": lock, "rules": rules,
    }
    for frame in frames.values():
        frame.columns = [str(c).strip().upper() for c in frame.columns]
    return frames


def load_data(force_demo: bool = False) -> DataBundle:
    """Load every dataset; fall back to demo data when nothing is on disk."""
    if force_demo:
        return DataBundle(build_demo_data(), is_demo=True,
                          messages=[("info", "Demo mode is on - showing synthetic data.")])

    frames: dict[str, pd.DataFrame] = {}
    messages: list[tuple[str, str]] = []
    for key, (folder, filename, label) in DATASET_REGISTRY.items():
        path = folder / filename
        if not path.exists():
            frames[key] = pd.DataFrame()
            messages.append(("warning", f"{label}: `{filename}` not found."))
            continue
        df, error = _read_csv_cached(str(path), path.stat().st_mtime)
        if error:
            LOGGER.warning("Could not read %s: %s", path, error)
            messages.append(("error", f"{label}: unable to read `{filename}` ({error})."))
        elif df.empty:
            messages.append(("warning", f"{label}: `{filename}` is empty."))
        frames[key] = df

    if not any(not df.empty for df in frames.values()):
        return DataBundle(
            build_demo_data(), is_demo=True,
            messages=[("info", "No CSV files found in `01_Data/` - showing synthetic demo data.")],
        )
    return DataBundle(frames, is_demo=False, messages=messages)


def apply_site_filter(frames: dict[str, pd.DataFrame], sites: Sequence[str]) -> dict[str, pd.DataFrame]:
    """Restrict every site-aware dataset to the selected sites (empty = all)."""
    if not sites:
        return dict(frames)
    selected = {s.strip().upper() for s in sites}
    result = dict(frames)
    for key in SITE_FILTERABLE_KEYS:
        df = frames.get(key, pd.DataFrame())
        if not df.empty and "SITE_ID" in df.columns:
            result[key] = df[col_upper(df, "SITE_ID").isin(selected)]
    return result


def collect_site_ids(frames: dict[str, pd.DataFrame]) -> list[str]:
    ids: set[str] = set()
    for key in ("sites", "subjects", "queries", "site_perf"):
        df = frames.get(key, pd.DataFrame())
        if not df.empty and "SITE_ID" in df.columns:
            ids.update(v for v in df["SITE_ID"].dropna().astype(str).str.strip() if v)
    return sorted(ids)


# ============================================================
# METRICS & DATABASE-LOCK LOGIC
# ============================================================

@dataclass(frozen=True)
class Kpis:
    sites: int
    subjects: int
    visits: int
    labs: int
    adverse_events: int
    deviations: int
    issues: int
    critical_issues: int
    major_issues: int
    minor_issues: int
    open_critical_issues: int
    queries: int
    active_queries: int
    closed_queries: int
    overdue_queries: int
    critical_active_queries: int
    closure_rate: float
    has_quality_data: bool
    has_query_data: bool


def compute_kpis(frames: dict[str, pd.DataFrame]) -> Kpis:
    sites, subjects = frames.get("sites", pd.DataFrame()), frames.get("subjects", pd.DataFrame())
    quality, queries = frames.get("quality", pd.DataFrame()), frames.get("queries", pd.DataFrame())

    subject_count = int(subjects["SUBJECT_ID"].nunique()) if "SUBJECT_ID" in subjects.columns else len(subjects)

    severity = col_upper(quality, "SEVERITY")
    critical_mask = severity.eq("CRITICAL")
    if "STATUS" in quality.columns:
        open_critical = int((critical_mask & ~col_upper(quality, "STATUS").isin(RESOLVED_ISSUE_STATUSES)).sum())
    else:
        open_critical = int(critical_mask.sum())

    status = col_upper(queries, "QUERY_STATUS")
    priority = col_upper(queries, "PRIORITY")
    aging = col_upper(queries, "AGING_BUCKET")
    active_mask = status.isin(ACTIVE_QUERY_STATUSES)
    overdue_mask = aging.isin(OVERDUE_BUCKETS)
    if "QUERY_STATUS" in queries.columns:
        overdue_mask = overdue_mask & active_mask  # only unresolved queries can be overdue
    closed = int(status.isin(CLOSED_QUERY_STATUSES).sum())
    total_queries = len(queries)

    return Kpis(
        sites=len(sites),
        subjects=subject_count,
        visits=len(frames.get("visits", pd.DataFrame())),
        labs=len(frames.get("labs", pd.DataFrame())),
        adverse_events=len(frames.get("aes", pd.DataFrame())),
        deviations=len(frames.get("deviations", pd.DataFrame())),
        issues=len(quality),
        critical_issues=int(critical_mask.sum()),
        major_issues=int(severity.eq("MAJOR").sum()),
        minor_issues=int(severity.eq("MINOR").sum()),
        open_critical_issues=open_critical,
        queries=total_queries,
        active_queries=int(active_mask.sum()),
        closed_queries=closed,
        overdue_queries=int(overdue_mask.sum()),
        critical_active_queries=int((priority.eq("CRITICAL") & active_mask).sum()),
        closure_rate=(closed / total_queries * 100) if total_queries else 0.0,
        has_quality_data=not quality.empty,
        has_query_data=not queries.empty,
    )


@dataclass(frozen=True)
class Gate:
    name: str
    passed: bool
    actual: str
    target: str


def evaluate_gates(k: Kpis) -> list[Gate]:
    """Transparent, data-driven database-lock gates."""
    return [
        Gate("No open critical data-quality findings", k.open_critical_issues == 0,
             fmt_int(k.open_critical_issues), "0"),
        Gate("No active critical-priority queries", k.critical_active_queries == 0,
             fmt_int(k.critical_active_queries), "0"),
        Gate("No overdue / critical-aged active queries", k.overdue_queries == 0,
             fmt_int(k.overdue_queries), "0"),
        Gate(f"Query closure rate >= {CLOSURE_RATE_TARGET:.0f}%", k.closure_rate >= CLOSURE_RATE_TARGET,
             f"{k.closure_rate:.1f}%", f">= {CLOSURE_RATE_TARGET:.0f}%"),
    ]


def lock_state(k: Kpis, gates: Sequence[Gate]) -> tuple[str, float]:
    """Return (READY | NOT READY | UNKNOWN, readiness score 0-100)."""
    if not (k.has_quality_data or k.has_query_data):
        return "UNKNOWN", 0.0
    passed = sum(g.passed for g in gates)
    score = passed / len(gates) * 100 if gates else 0.0
    return ("READY" if passed == len(gates) else "NOT READY"), score


@dataclass(frozen=True)
class AppContext:
    frames: dict[str, pd.DataFrame]
    kpis: Kpis
    gates: list[Gate]
    lock_status: str
    lock_score: float
    is_demo: bool

    def df(self, key: str) -> pd.DataFrame:
        return self.frames.get(key, pd.DataFrame())


def build_insights(ctx: AppContext) -> list[str]:
    """Auto-generated plain-language findings for the executive summary."""
    k, notes = ctx.kpis, []
    if k.open_critical_issues:
        notes.append(f"**{fmt_int(k.open_critical_issues)}** open critical data-quality findings block database lock.")
    if k.critical_active_queries:
        notes.append(f"**{fmt_int(k.critical_active_queries)}** critical-priority queries are still active.")
    if k.overdue_queries:
        notes.append(f"**{fmt_int(k.overdue_queries)}** active queries are overdue or critically aged.")
    if k.queries:
        verdict = "meets" if k.closure_rate >= CLOSURE_RATE_TARGET else "is below"
        notes.append(f"Query closure rate is **{k.closure_rate:.1f}%** and {verdict} the {CLOSURE_RATE_TARGET:.0f}% target.")
    perf = ctx.df("site_perf")
    scores = numeric(perf, "QUALITY_SCORE").dropna()
    if not scores.empty and "SITE_ID" in perf.columns:
        worst, best = scores.idxmin(), scores.idxmax()
        notes.append(f"Lowest quality score: **{perf.loc[worst, 'SITE_ID']}** ({scores[worst]:.1f}); "
                     f"highest: **{perf.loc[best, 'SITE_ID']}** ({scores[best]:.1f}).")
    if not notes and ctx.lock_status == "READY":
        notes.append("All database-lock gates pass - the study is ready for lock review.")
    return notes or ["No quality or query data available to summarise."]


# ============================================================
# STYLING & RICH HTML COMPONENTS
# ============================================================

GLOBAL_CSS = """
<style>
.stApp {
  background: radial-gradient(1200px 600px at 10% -10%, rgba(56,189,248,.10), transparent 60%),
              radial-gradient(900px 500px at 100% 0%, rgba(167,139,250,.10), transparent 55%),
              #0b1220;
}
[data-testid="stSidebar"] { background: linear-gradient(180deg,#0f172a,#0b1220); border-right: 1px solid rgba(148,163,184,.15); }
.block-container { padding-top: 1.4rem; padding-bottom: 3rem; animation: fadeUp .5s ease both; }
@keyframes fadeUp { from {opacity:0; transform: translateY(10px);} to {opacity:1; transform:none;} }
h1,h2,h3 { letter-spacing: -0.01em; }
[data-testid="stMetric"] {
  background: linear-gradient(145deg, rgba(30,41,59,.75), rgba(15,23,42,.85));
  border: 1px solid rgba(148,163,184,.18); border-radius: 14px; padding: 14px 16px;
  transition: transform .2s ease, border-color .2s ease;
}
[data-testid="stMetric"]:hover { transform: translateY(-3px); border-color: rgba(56,189,248,.5); }
.stTabs [data-baseweb="tab"] { border-radius: 10px 10px 0 0; }
.cdm-banner { padding: 14px 18px; border-radius: 14px; font-weight: 600; margin: 6px 0 14px 0;
  border: 1px solid rgba(148,163,184,.2); animation: fadeUp .5s ease both; }
.cdm-banner.ok { background: rgba(52,211,153,.12); color: #34d399; border-color: rgba(52,211,153,.4); }
.cdm-banner.bad { background: rgba(248,113,113,.12); color: #f87171; border-color: rgba(248,113,113,.4);
  animation: fadeUp .5s ease both, pulse 2.4s ease-in-out infinite; }
.cdm-banner.unk { background: rgba(251,191,36,.12); color: #fbbf24; border-color: rgba(251,191,36,.4); }
@keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(248,113,113,.35);} 50% { box-shadow: 0 0 0 8px rgba(248,113,113,0);} }
.cdm-insight { padding: 8px 14px; margin: 6px 0; border-left: 3px solid #38bdf8; background: rgba(56,189,248,.06);
  border-radius: 0 10px 10px 0; }
</style>
"""

_BASE_HTML_HEAD = (
    "<!doctype html><html><head><meta charset='utf-8'><style>"
    "*{box-sizing:border-box}"
    "body{margin:0;font-family:'Inter','Segoe UI',system-ui,sans-serif;background:transparent;color:#e2e8f0}"
)

_HERO_TEMPLATE = _BASE_HTML_HEAD + """
.hero{position:relative;height:176px;border-radius:20px;overflow:hidden;display:flex;align-items:center;
  background:linear-gradient(120deg,#0f172a,#1e1b4b,#0c4a6e,#0f172a);background-size:300% 300%;
  animation:flow 14s ease infinite;border:1px solid rgba(148,163,184,.22)}
@keyframes flow{0%{background-position:0% 50%}50%{background-position:100% 50%}100%{background-position:0% 50%}}
.text{position:relative;z-index:2;padding:0 30px;flex:1}
h1{margin:0 0 6px 0;font-size:28px;line-height:1.15;background:linear-gradient(90deg,#e0f2fe,#c4b5fd);
  -webkit-background-clip:text;background-clip:text;color:transparent}
p{margin:0 0 12px 0;color:#94a3b8;font-size:14px}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid rgba(148,163,184,.3);
  background:rgba(15,23,42,.55);color:#cbd5e1}
.chip.mode{border-color:rgba(52,211,153,.5);color:#34d399}
.chip.demo{border-color:rgba(251,191,36,.5);color:#fbbf24}
canvas{position:absolute;right:0;top:0;height:100%;width:38%;z-index:1;opacity:.95}
@media(max-width:700px){canvas{display:none}}
</style></head><body>
<div class="hero">
  <div class="text">
    <h1>🧬 __TITLE__</h1>
    <p>Clinical Data Management &bull; Data Quality &bull; Query Management &bull; Database Lock Readiness</p>
    <div class="chips"><span class="chip __MODE_CLASS__">__MODE__</span>
      <span class="chip">Data &rarr; Cleaning &rarr; Validation &rarr; Queries &rarr; Quality &rarr; Lock</span></div>
  </div>
  <canvas id="helix"></canvas>
</div>
<script>
(function(){
  var c=document.getElementById('helix'),ctx=c.getContext('2d'),t=0,dpr=window.devicePixelRatio||1;
  var calm=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function resize(){var r=c.getBoundingClientRect();c.width=r.width*dpr;c.height=r.height*dpr;}
  window.addEventListener('resize',resize);resize();
  function draw(){
    var w=c.width,h=c.height,cx=w/2,R=Math.min(w*0.28,h*0.42),N=30,pts=[];
    ctx.clearRect(0,0,w,h);
    for(var i=0;i<N;i++){
      var y=h*0.06+(h*0.88)*i/(N-1),a=t+i*0.42,s=Math.sin(a),co=Math.cos(a);
      pts.push({y:y,x1:cx+R*co,z1:s,x2:cx-R*co,z2:-s});
    }
    pts.forEach(function(p){
      var al=0.15+0.25*((p.z1+1)/2);
      ctx.strokeStyle='rgba(148,163,184,'+al+')';ctx.lineWidth=1.4*dpr;
      ctx.beginPath();ctx.moveTo(p.x1,p.y);ctx.lineTo(p.x2,p.y);ctx.stroke();
    });
    var dots=[];
    pts.forEach(function(p){dots.push({x:p.x1,y:p.y,z:p.z1,c:'56,189,248'});dots.push({x:p.x2,y:p.y,z:p.z2,c:'167,139,250'});});
    dots.sort(function(a,b){return a.z-b.z;});
    dots.forEach(function(d){
      var k=(d.z+1)/2,r=(2.6+3.6*k)*dpr;
      ctx.fillStyle='rgba('+d.c+','+(0.35+0.65*k)+')';
      ctx.beginPath();ctx.arc(d.x,d.y,r,0,Math.PI*2);ctx.fill();
    });
    if(!calm)t+=0.025;
    requestAnimationFrame(draw);
  }
  draw();
})();
</script></body></html>
"""

_KPI_TEMPLATE = _BASE_HTML_HEAD + """
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;perspective:900px;padding:4px}
@media(max-width:900px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.card{position:relative;padding:16px 18px;border-radius:16px;
  background:linear-gradient(145deg,rgba(30,41,59,.85),rgba(15,23,42,.92));
  border:1px solid rgba(148,163,184,.18);box-shadow:0 8px 24px rgba(0,0,0,.35);
  transform-style:preserve-3d;transition:transform .15s ease,box-shadow .2s ease;
  opacity:0;animation:rise .6s ease forwards;overflow:hidden}
.card:before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent)}
.card:hover{box-shadow:0 14px 34px rgba(0,0,0,.5),0 0 0 1px var(--accent)}
@keyframes rise{from{opacity:0;transform:translateY(14px) rotateX(18deg)}to{opacity:1;transform:none}}
.icon{font-size:20px;margin-bottom:4px}
.label{font-size:12px;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8}
.value{font-size:30px;font-weight:700;color:var(--accent);margin-top:2px;font-variant-numeric:tabular-nums}
.note{font-size:12px;color:#64748b;margin-top:2px;min-height:15px}
</style></head><body><div class="grid">__CARDS__</div>
<script>
document.querySelectorAll('.value').forEach(function(el){
  var target=parseFloat(el.dataset.target)||0,dec=parseInt(el.dataset.dec||'0'),suf=el.dataset.suffix||'',t0=performance.now();
  function step(now){
    var p=Math.min((now-t0)/1100,1),e=1-Math.pow(1-p,3);
    el.textContent=(target*e).toLocaleString(undefined,{minimumFractionDigits:dec,maximumFractionDigits:dec})+suf;
    if(p<1)requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
});
document.querySelectorAll('.card').forEach(function(card){
  card.addEventListener('mousemove',function(e){
    var r=card.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
    card.style.transform='rotateY('+(x*14)+'deg) rotateX('+(-y*14)+'deg) translateZ(8px)';
  });
  card.addEventListener('mouseleave',function(){card.style.transform='';});
});
</script></body></html>
"""


@dataclass(frozen=True)
class KpiCard:
    label: str
    value: float
    icon: str = "📌"
    accent: str = COLORS["primary"]
    decimals: int = 0
    suffix: str = ""
    note: str = ""


def render_html(markup: str, height: int, scrolling: bool = False) -> None:
    """Render a self-contained HTML/JS snippet in an iframe.

    Uses ``st.iframe`` on current Streamlit; ``components.html`` is deprecated there
    and only kept as a fallback for older releases. ``markup`` must only ever contain
    app-generated HTML (all data values are escaped before they get here).
    """
    if hasattr(st, "iframe"):
        st.iframe(markup, height=height)
    else:  # pragma: no cover - older Streamlit
        components.html(markup, height=height, scrolling=scrolling)


def render_hero(is_demo: bool) -> None:
    mode = "DEMO DATA" if is_demo else "LIVE DATA"
    markup = (
        _HERO_TEMPLATE
        .replace("__TITLE__", html.escape(APP_TITLE))
        .replace("__MODE__", mode)
        .replace("__MODE_CLASS__", "demo" if is_demo else "mode")
    )
    render_html(markup, height=190)


def render_kpi_cards(cards: Sequence[KpiCard]) -> None:
    """Animated count-up KPI cards with a 3D hover tilt."""
    items = []
    for index, card in enumerate(cards):
        items.append(
            f"<div class='card' style='--accent:{card.accent};animation-delay:{index * 0.06:.2f}s'>"
            f"<div class='icon'>{html.escape(card.icon)}</div>"
            f"<div class='label'>{html.escape(card.label)}</div>"
            f"<div class='value' data-target='{safe_float(card.value)}' data-dec='{card.decimals}' "
            f"data-suffix='{html.escape(card.suffix)}'>0</div>"
            f"<div class='note'>{html.escape(card.note)}</div></div>"
        )
    rows = max(1, math.ceil(len(cards) / 4))
    render_html(_KPI_TEMPLATE.replace("__CARDS__", "".join(items)), height=rows * 136 + 12, scrolling=True)


def lock_banner(status: str, score: float) -> None:
    css, text = {
        "READY": ("ok", f"✅ DATABASE LOCK: READY - all gates passed ({score:.0f}%)"),
        "NOT READY": ("bad", f"⛔ DATABASE LOCK: NOT READY - readiness {score:.0f}%; blocking gates remain"),
    }.get(status, ("unk", "⚠️ DATABASE LOCK: UNKNOWN - no quality or query data available"))
    st.markdown(f"<div class='cdm-banner {css}'>{html.escape(text)}</div>", unsafe_allow_html=True)


# ============================================================
# PLOTTING HELPERS
# ============================================================

def style_fig(fig: go.Figure, height: int = 400, title: str | None = None) -> go.Figure:
    fig.update_layout(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", color=COLORS["text"]),
        colorway=PALETTE,
        margin=dict(l=20, r=20, t=56 if title else 20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    if title:
        fig.update_layout(title=dict(text=title, x=0.01, font=dict(size=16)))
    return fig


def show_chart(fig: go.Figure, key: str) -> None:
    st.plotly_chart(fig, key=key, **STRETCH)


def show_df(
    df: pd.DataFrame,
    height: int | None = None,
    column_config: dict[str, Any] | None = None,
) -> None:
    kwargs: dict[str, Any] = {"hide_index": True, **STRETCH}
    if height:
        kwargs["height"] = height
    if column_config:
        kwargs["column_config"] = column_config
    st.dataframe(df, **kwargs)


def notice(message: str, level: str = "warning") -> None:
    {"warning": st.warning, "info": st.info, "error": st.error}.get(level, st.warning)(message)


def bar_chart(df: pd.DataFrame, x: str, y: str, title: str, key: str, color: str | None = None,
              color_map: dict[str, str] | None = None, height: int = 380, horizontal: bool = False) -> None:
    if df.empty:
        notice("Not enough data to draw this chart.", "info")
        return
    fig = px.bar(df, x=y if horizontal else x, y=x if horizontal else y, color=color,
                 color_discrete_map=color_map, text_auto=True, orientation="h" if horizontal else "v")
    fig.update_traces(marker_line_width=0, textposition="outside", cliponaxis=False)
    show_chart(style_fig(fig, height, title), key)


def donut_chart(df: pd.DataFrame, names: str, title: str, key: str,
                color_map: dict[str, str] | None = None, height: int = 380) -> None:
    if df.empty:
        notice("Not enough data to draw this chart.", "info")
        return
    fig = px.pie(df, names=names, values="COUNT", hole=0.55, color=names, color_discrete_map=color_map)
    fig.update_traces(textinfo="percent+label", pull=[0.03] * len(df), sort=False)
    show_chart(style_fig(fig, height, title), key)


def readiness_gauge(score: float, key: str) -> None:
    color = COLORS["success"] if score >= 100 else COLORS["warning"] if score >= 50 else COLORS["danger"]
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number={"suffix": "%", "font": {"size": 44}},
        title={"text": "Lock Readiness"},
        gauge={
            "axis": {"range": [0, 100]},
            "bar": {"color": color, "thickness": 0.28},
            "bgcolor": "rgba(0,0,0,0)",
            "steps": [
                {"range": [0, 50], "color": "rgba(248,113,113,.18)"},
                {"range": [50, 99.99], "color": "rgba(251,191,36,.16)"},
                {"range": [99.99, 100], "color": "rgba(52,211,153,.35)"},
            ],
        },
    ))
    show_chart(style_fig(fig, 300), key)


# ---------- 3D helpers --------------------------------------------------

_CUBE_I = [7, 0, 0, 0, 4, 4, 6, 1, 4, 0, 3, 6]
_CUBE_J = [3, 4, 1, 2, 5, 6, 5, 2, 0, 1, 6, 3]
_CUBE_K = [0, 7, 2, 3, 6, 7, 1, 6, 5, 5, 7, 2]


def _cuboid(x0: float, y0: float, dx: float, dy: float, dz: float, color: str, hover: str) -> go.Mesh3d:
    return go.Mesh3d(
        x=[x0, x0, x0 + dx, x0 + dx, x0, x0, x0 + dx, x0 + dx],
        y=[y0, y0 + dy, y0 + dy, y0, y0, y0 + dy, y0 + dy, y0],
        z=[0, 0, 0, 0, dz, dz, dz, dz],
        i=_CUBE_I, j=_CUBE_J, k=_CUBE_K,
        color=color, opacity=0.95, flatshading=True,
        hovertext=hover, hoverinfo="text", showlegend=False,
        lighting=dict(ambient=0.55, diffuse=0.8, specular=0.25),
    )


def bars_3d(matrix: pd.DataFrame, x_title: str, y_title: str, title: str) -> go.Figure:
    """3D bar chart from a (rows x columns) count matrix, built from Mesh3d cuboids."""
    vmax = float(matrix.to_numpy().max()) if matrix.size else 0.0
    fig = go.Figure()
    for yi, row_label in enumerate(matrix.index):
        for xi, col_label in enumerate(matrix.columns):
            value = float(matrix.iloc[yi, xi])
            if value <= 0:
                continue
            shade = px.colors.sample_colorscale("Turbo", [0.15 + 0.8 * value / vmax])[0] if vmax else COLORS["primary"]
            fig.add_trace(_cuboid(xi, yi, 0.72, 0.72, value, shade,
                                  f"{col_label}<br>{row_label}<br><b>{int(value)}</b> queries"))
    fig.update_layout(scene=dict(
        xaxis=dict(title=x_title, tickvals=[i + 0.36 for i in range(len(matrix.columns))],
                   ticktext=[str(c) for c in matrix.columns]),
        yaxis=dict(title=y_title, tickvals=[i + 0.36 for i in range(len(matrix.index))],
                   ticktext=[str(r) for r in matrix.index]),
        zaxis=dict(title="Count"),
        camera=dict(eye=dict(x=1.7, y=-1.7, z=1.0)),
        aspectmode="cube",
    ))
    return style_fig(fig, 560, title)


_AUTO_ROTATE_JS = """
var gd = document.getElementById('{plot_id}');
var angle = Math.atan2(__EY__, __EX__), radius = Math.hypot(__EX__, __EY__), zeye = __EZ__;
var running = true, resumeTimer = null;
function pause(){ running = false; if (resumeTimer) clearTimeout(resumeTimer); }
function resume(){ if (resumeTimer) clearTimeout(resumeTimer); resumeTimer = setTimeout(function(){ running = true; }, 2500); }
gd.addEventListener('mousedown', pause); gd.addEventListener('touchstart', pause);
gd.addEventListener('mouseup', resume); gd.addEventListener('touchend', resume);
function spin(){
  if (running) {
    angle += __SPEED__;
    Plotly.relayout(gd, {'scene.camera.eye': {x: radius*Math.cos(angle), y: radius*Math.sin(angle), z: zeye}});
  }
  requestAnimationFrame(spin);
}
spin();
"""


def render_auto_rotating(fig: go.Figure, key: str, height: int, speed: float = 0.006,
                         eye: tuple[float, float, float] = (1.7, 1.7, 0.9)) -> None:
    """Auto-rotating 3D plot. Falls back to a normal chart if HTML export fails.

    The standalone page loads plotly.js from a CDN, so it needs an internet connection.
    Dragging the plot pauses rotation; it resumes after 2.5 s of inactivity.
    """
    try:
        script = (_AUTO_ROTATE_JS.replace("__EX__", str(eye[0])).replace("__EY__", str(eye[1]))
                  .replace("__EZ__", str(eye[2])).replace("__SPEED__", str(speed)))
        fig.update_layout(scene_camera=dict(eye=dict(x=eye[0], y=eye[1], z=eye[2])), autosize=True)
        div = fig.to_html(full_html=False, include_plotlyjs="cdn", post_script=script,
                          default_height=f"{height}px", default_width="100%",
                          config={"displaylogo": False, "responsive": True})
        render_html(_BASE_HTML_HEAD + "html,body{overflow:hidden}</style></head><body>" + div + "</body></html>",
                    height=height + 6)
    except Exception as exc:  # noqa: BLE001 - never let a visual break the page
        LOGGER.warning("Auto-rotate render failed: %s", exc)
        show_chart(fig, key)


# ============================================================
# TABLE FILTER HELPER
# ============================================================

def filter_table(df: pd.DataFrame, key: str, filter_columns: Sequence[str] = ()) -> pd.DataFrame:
    """Render multiselect + search filters above a table and return the filtered frame."""
    usable = [c for c in filter_columns if c in df.columns]
    widgets = st.columns(len(usable) + 1)
    out = df
    for widget, column in zip(widgets, usable):
        options = ordered(col_upper(df, column).unique(), PRIORITY_ORDER + STATUS_ORDER + SEVERITY_ORDER)
        picked = widget.multiselect(column.replace("_", " ").title(), options, key=f"{key}_{column}")
        if picked:
            out = out[col_upper(out, column).isin(picked)]
    term = widgets[-1].text_input("Search", key=f"{key}_search", placeholder="Type to search all columns")
    if term.strip():
        text = out.astype(str)
        mask = text.apply(lambda s: s.str.contains(term.strip(), case=False, na=False, regex=False)).any(axis=1)
        out = out[mask]
    st.caption(f"Showing {len(out):,} of {len(df):,} records")
    return out


# ============================================================
# PAGES
# ============================================================

def page_executive(ctx: AppContext) -> None:
    st.subheader("📊 Executive Dashboard")
    k = ctx.kpis
    lock_banner(ctx.lock_status, ctx.lock_score)

    render_kpi_cards([
        KpiCard("Clinical Sites", k.sites, "🏥", COLORS["primary"]),
        KpiCard("Subjects", k.subjects, "🧑‍⚕️", COLORS["accent"]),
        KpiCard("Quality Issues", k.issues, "🔎", COLORS["warning"], note=f"{fmt_int(k.critical_issues)} critical"),
        KpiCard("Total Queries", k.queries, "📨", COLORS["primary"], note=f"{k.closure_rate:.1f}% closed"),
        KpiCard("Active Queries", k.active_queries, "⏳", COLORS["orange"]),
        KpiCard("Overdue Active Queries", k.overdue_queries, "🚨", COLORS["danger"],
                note=f"{fmt_int(k.critical_active_queries)} critical-priority"),
        KpiCard("Adverse Events", k.adverse_events, "💊", COLORS["accent"]),
        KpiCard("Protocol Deviations", k.deviations, "⚠️", COLORS["warning"]),
    ])

    st.markdown("#### 🧠 Key findings")
    for note in build_insights(ctx):
        st.markdown(f"<div class='cdm-insight'>{note}</div>", unsafe_allow_html=True)

    st.divider()
    left, right = st.columns([1, 2])
    with left:
        readiness_gauge(ctx.lock_score, "exec_gauge")
    with right:
        queries = ctx.df("queries")
        status = count_frame(col_upper(queries, "QUERY_STATUS"), "QUERY_STATUS", STATUS_ORDER)
        bar_chart(status, "QUERY_STATUS", "COUNT", "Query status distribution", "exec_status", height=300)

    left, right = st.columns(2)
    with left:
        severity = count_frame(col_upper(ctx.df("quality"), "SEVERITY"), "SEVERITY", SEVERITY_ORDER)
        donut_chart(severity, "SEVERITY", "Quality findings by severity", "exec_severity", SEVERITY_COLORS)
    with right:
        priority = count_frame(col_upper(queries, "PRIORITY"), "PRIORITY", PRIORITY_ORDER)
        donut_chart(priority, "PRIORITY", "Queries by priority", "exec_priority", PRIORITY_COLORS)

    kpi_df = ctx.df("kpi")
    if not kpi_df.empty:
        with st.expander("📈 Pipeline KPI summary (from kpi_summary.csv)"):
            show_df(kpi_df)


def page_overview(ctx: AppContext) -> None:
    st.subheader("📁 Clinical Trial Data Overview")
    rows = []
    for key in CLINICAL_KEYS:
        df = ctx.df(key)
        cells = df.size
        missing = float(df.isna().sum().sum() / cells * 100) if cells else 0.0
        rows.append({
            "Dataset": DATASET_REGISTRY[key][2], "Records": len(df), "Columns": len(df.columns),
            "Completeness %": round(100 - missing, 1) if cells else 0.0,
            "Status": "Loaded" if not df.empty else "Missing / empty",
        })
    overview = pd.DataFrame(rows)

    left, right = st.columns([3, 2])
    with left:
        show_df(overview, column_config={
            "Completeness %": st.column_config.ProgressColumn("Completeness %", min_value=0, max_value=100, format="%.1f"),
        })
    with right:
        loaded = overview[overview["Records"] > 0]
        if loaded.empty:
            notice("No clinical datasets are loaded.", "info")
        else:
            fig = px.treemap(loaded, path=["Dataset"], values="Records", color="Completeness %",
                             color_continuous_scale="Tealgrn")
            show_chart(style_fig(fig, 320, "Dataset volume map"), "overview_treemap")

    bar_chart(overview[overview["Records"] > 0], "Dataset", "Records", "Records per dataset", "overview_bar")

    with st.expander("🧾 Column schema by dataset"):
        key = st.selectbox("Dataset", CLINICAL_KEYS, format_func=lambda k: DATASET_REGISTRY[k][2], key="schema_pick")
        df = ctx.df(key)
        if df.empty:
            notice("This dataset is empty or unavailable.", "info")
        else:
            show_df(pd.DataFrame({"Column": df.columns, "Type": [str(t) for t in df.dtypes],
                                  "Missing": df.isna().sum().to_numpy(),
                                  "Unique": df.nunique(dropna=True).to_numpy()}))


def page_quality(ctx: AppContext) -> None:
    st.subheader("🔎 Data Quality Monitoring")
    quality, k = ctx.df("quality"), ctx.kpis
    if quality.empty:
        notice("No data quality results found (`data_quality_results.csv`).")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total findings", fmt_int(k.issues))
    c2.metric("Critical", fmt_int(k.critical_issues))
    c3.metric("Major", fmt_int(k.major_issues))
    c4.metric("Minor", fmt_int(k.minor_issues))
    st.divider()

    severity = col_upper(quality, "SEVERITY")
    left, right = st.columns(2)
    with left:
        bar_chart(count_frame(severity, "SEVERITY", SEVERITY_ORDER), "SEVERITY", "COUNT",
                  "Findings by severity", "dq_severity", color="SEVERITY", color_map=SEVERITY_COLORS)
    with right:
        dataset_col = find_column(quality, QUALITY_DATASET_COLUMNS)
        if dataset_col:
            bar_chart(count_frame(col_upper(quality, dataset_col), dataset_col).head(15), dataset_col, "COUNT",
                      f"Findings by {dataset_col.lower().replace('_', ' ')}", "dq_dataset", horizontal=True)
        else:
            notice("No dataset/table column found for a breakdown.", "info")

    if "SITE_ID" in quality.columns and severity.ne("").any():
        top_sites = col_upper(quality, "SITE_ID").value_counts().head(15).index
        stacked = pd.DataFrame({"SITE_ID": col_upper(quality, "SITE_ID"), "SEVERITY": severity})
        stacked = stacked[stacked["SITE_ID"].isin(top_sites) & stacked["SEVERITY"].ne("")]
        stacked = stacked.groupby(["SITE_ID", "SEVERITY"]).size().reset_index(name="COUNT")
        fig = px.bar(stacked, x="SITE_ID", y="COUNT", color="SEVERITY", color_discrete_map=SEVERITY_COLORS,
                     category_orders={"SEVERITY": list(SEVERITY_ORDER)})
        show_chart(style_fig(fig, 380, "Findings by site (top 15) and severity"), "dq_site_stack")

    st.markdown("#### Validation findings")
    show_df(filter_table(quality, "dq", ("SEVERITY", "STATUS")), height=460)


def page_queries(ctx: AppContext) -> None:
    st.subheader("📨 Query Management")
    queries, k = ctx.df("queries"), ctx.kpis
    if queries.empty:
        notice("No queries found (`queries.csv`).")
        return

    status = col_upper(queries, "QUERY_STATUS")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total", fmt_int(k.queries))
    c2.metric("Closed", fmt_int(status.eq("CLOSED").sum()))
    c3.metric("Resolved", fmt_int(status.eq("RESOLVED").sum()))
    c4.metric("Active", fmt_int(k.active_queries))
    c5.metric("Overdue (active)", fmt_int(k.overdue_queries))
    st.divider()

    left, right = st.columns(2)
    with left:
        donut_chart(count_frame(status, "STATUS", STATUS_ORDER), "STATUS", "Query status", "q_status")
    with right:
        bar_chart(count_frame(col_upper(queries, "AGING_BUCKET"), "AGING", AGING_ORDER), "AGING", "COUNT",
                  "Query aging", "q_aging")

    priority = col_upper(queries, "PRIORITY")
    if priority.ne("").any() and status.ne("").any():
        matrix = pd.crosstab(priority[priority.ne("")], status[status.ne("")])
        matrix = matrix.reindex(index=ordered(matrix.index, PRIORITY_ORDER),
                                columns=ordered(matrix.columns, STATUS_ORDER))
        fig = px.imshow(matrix, text_auto=True, aspect="auto", color_continuous_scale="Viridis")
        show_chart(style_fig(fig, 320, "Priority x status heatmap"), "q_heat")

    st.markdown("#### Query register")
    show_df(filter_table(queries, "qr", ("QUERY_STATUS", "PRIORITY", "AGING_BUCKET")), height=460)


def page_sites(ctx: AppContext) -> None:
    st.subheader("🏥 Site Performance")
    perf = ctx.df("site_perf")
    if perf.empty:
        notice("No site performance data found (`site_performance.csv`).")
        return
    perf = perf.copy()
    for column in ("QUALITY_SCORE", "QUERY_RESOLUTION_RATE_PCT", "SUBJECTS"):
        if column in perf.columns:
            perf[column] = numeric(perf, column)

    config: dict[str, Any] = {}
    for column in ("QUALITY_SCORE", "QUERY_RESOLUTION_RATE_PCT"):
        if column in perf.columns:
            config[column] = st.column_config.ProgressColumn(
                column.replace("_", " ").title(), min_value=0, max_value=100, format="%.1f")

    if "QUALITY_SCORE" in perf.columns:
        threshold = st.slider("Attention threshold (quality score below)", 0, 100, 80, key="site_threshold")
        low = perf[perf["QUALITY_SCORE"] < threshold]
        m1, m2, m3 = st.columns(3)
        m1.metric("Sites", fmt_int(len(perf)))
        m2.metric("Average quality score", f"{perf['QUALITY_SCORE'].mean():.1f}")
        m3.metric(f"Sites below {threshold}", fmt_int(len(low)))
        st.divider()

        ranked = perf.dropna(subset=["QUALITY_SCORE"]).sort_values("QUALITY_SCORE", ascending=False)
        if "SITE_ID" in ranked.columns and not ranked.empty:
            fig = px.bar(ranked.head(15), x="SITE_ID", y="QUALITY_SCORE", color="QUALITY_SCORE",
                         color_continuous_scale="Tealgrn", range_y=[0, 100])
            show_chart(style_fig(fig, 360, "Top 15 sites by quality score"), "site_top")

    if {"QUERY_RESOLUTION_RATE_PCT", "QUALITY_SCORE"} <= set(perf.columns):
        plot = perf.dropna(subset=["QUERY_RESOLUTION_RATE_PCT", "QUALITY_SCORE"])
        size = "SUBJECTS" if "SUBJECTS" in plot.columns and plot["SUBJECTS"].fillna(0).gt(0).any() else None
        if size:
            plot = plot.assign(SUBJECTS=plot["SUBJECTS"].fillna(0).clip(lower=1))
        fig = px.scatter(plot, x="QUERY_RESOLUTION_RATE_PCT", y="QUALITY_SCORE", size=size, size_max=38,
                         hover_name="SITE_ID" if "SITE_ID" in plot.columns else None,
                         color="QUALITY_SCORE", color_continuous_scale="Turbo")
        show_chart(style_fig(fig, 400, "Query resolution rate vs quality score"), "site_scatter")
        st.caption("Tip: open the 🧊 3D Lab for the rotating 3D version of this chart.")

    show_df(perf, height=420, column_config=config)


def page_deviations(ctx: AppContext) -> None:
    st.subheader("⚠️ Protocol Deviations")
    dev = ctx.df("deviations")
    if dev.empty:
        notice("No protocol deviation data found (`protocol_deviations.csv`).")
        return

    st.metric("Total protocol deviations", fmt_int(len(dev)))
    left, right = st.columns(2)
    with left:
        if "SITE_ID" in dev.columns:
            by_site = count_frame(col_upper(dev, "SITE_ID"), "SITE_ID").head(20)
            bar_chart(by_site, "SITE_ID", "COUNT", "Deviations by site (top 20)", "dev_site")
    with right:
        category = find_column(dev, DEVIATION_CATEGORY_COLUMNS)
        if category:
            donut_chart(count_frame(col_upper(dev, category), category), category,
                        f"Deviations by {category.lower().replace('_', ' ')}", "dev_category")
    show_df(filter_table(dev, "dev", tuple(c for c in DEVIATION_CATEGORY_COLUMNS if c in dev.columns)[:1]), height=440)


def page_lock(ctx: AppContext) -> None:
    st.subheader("🔒 Database Lock Readiness")
    lock_banner(ctx.lock_status, ctx.lock_score)

    left, right = st.columns([1, 2])
    with left:
        readiness_gauge(ctx.lock_score, "lock_gauge")
    with right:
        st.markdown("#### Gate evaluation")
        gates = pd.DataFrame([{
            "Gate": g.name, "Result": "✅ PASS" if g.passed else "❌ FAIL", "Actual": g.actual, "Target": g.target,
        } for g in ctx.gates])
        show_df(gates)
        st.caption("Gates are computed live from the current (site-filtered) data.")

    lock_df = ctx.df("lock")
    st.divider()
    st.markdown("#### Lock readiness report (from file)")
    if lock_df.empty:
        notice("`database_lock_readiness.csv` not found - showing computed gates only.", "info")
    else:
        show_df(lock_df)
        blockers: list[str] = []
        for column in lock_df.columns:
            for value in lock_df[column].dropna().astype(str):
                lowered = value.lower()
                if any(word in lowered for word in ("critical", "blocking", "not ready")):
                    blockers.append(value)
        for value in dict.fromkeys(blockers):  # de-duplicate, keep order
            st.warning(value)


def page_rules(ctx: AppContext) -> None:
    st.subheader("📋 Validation Rule Catalog")
    rules = ctx.df("rules")
    if rules.empty:
        notice("`validation_rule_catalog.csv` not found.")
        return
    c1, c2 = st.columns([1, 2])
    c1.metric("Registered validation rules", fmt_int(len(rules)))
    if "SEVERITY" in rules.columns:
        with c2:
            bar_chart(count_frame(col_upper(rules, "SEVERITY"), "SEVERITY", SEVERITY_ORDER), "SEVERITY", "COUNT",
                      "Rules by severity", "rules_sev", color="SEVERITY", color_map=SEVERITY_COLORS, height=260)
    show_df(filter_table(rules, "rules", ("SEVERITY", "DATASET")), height=520)


def _site_scatter_frame(ctx: AppContext) -> pd.DataFrame:
    perf = ctx.df("site_perf")
    needed = {"SITE_ID", "QUALITY_SCORE", "QUERY_RESOLUTION_RATE_PCT"}
    if perf.empty or not needed <= set(perf.columns):
        return pd.DataFrame()
    out = perf[["SITE_ID"]].copy()
    out["QUALITY"] = numeric(perf, "QUALITY_SCORE")
    out["RESOLUTION"] = numeric(perf, "QUERY_RESOLUTION_RATE_PCT")
    out["SUBJECTS"] = numeric(perf, "SUBJECTS").fillna(1).clip(lower=1) if "SUBJECTS" in perf.columns else 1.0
    if "DEVIATIONS" in perf.columns:
        out["DEVIATIONS"] = numeric(perf, "DEVIATIONS").fillna(0)
    else:
        dev = ctx.df("deviations")
        counts = col_upper(dev, "SITE_ID").value_counts() if "SITE_ID" in dev.columns else pd.Series(dtype=int)
        out["DEVIATIONS"] = out["SITE_ID"].astype(str).str.strip().str.upper().map(counts).fillna(0)
    return out.dropna(subset=["QUALITY", "RESOLUTION"])


def _cumulative_by_month(queries: pd.DataFrame, date_col: str) -> pd.DataFrame:
    dates = pd.to_datetime(queries[date_col], errors="coerce")
    cats = col_upper(queries, "PRIORITY") if "PRIORITY" in queries.columns else pd.Series("ALL", index=queries.index)
    tmp = pd.DataFrame({"DATE": dates, "PRIORITY": cats}).dropna(subset=["DATE"])
    tmp = tmp[tmp["PRIORITY"] != ""]
    if tmp.empty:
        return pd.DataFrame()
    tmp["MONTH"] = tmp["DATE"].dt.to_period("M")
    grid = tmp.groupby(["MONTH", "PRIORITY"]).size().unstack(fill_value=0)
    grid = grid.reindex(pd.period_range(grid.index.min(), grid.index.max(), freq="M"), fill_value=0).cumsum()
    grid = grid.tail(36)
    grid.index = grid.index.astype(str)
    grid.index.name = "MONTH"
    long = grid.reset_index().melt(id_vars="MONTH", var_name="PRIORITY", value_name="CUMULATIVE")
    return long


def page_3d_lab(ctx: AppContext) -> None:
    st.subheader("🧊 3D Lab")
    st.caption("Interactive 3D views - drag to rotate, scroll to zoom, hover for details.")
    auto = st.toggle("Auto-rotate 3D scatter (loads plotly.js from the internet)", value=False, key="lab_auto")

    t1, t2, t3, t4 = st.tabs(["🌌 Site Galaxy", "🧱 3D Query Bars", "🏔️ Query Terrain", "🎞️ Timeline Animation"])

    with t1:
        frame = _site_scatter_frame(ctx)
        if frame.empty:
            notice("Needs `site_performance.csv` with SITE_ID, QUALITY_SCORE and QUERY_RESOLUTION_RATE_PCT.", "info")
        else:
            size = 8 + 24 * (frame["SUBJECTS"] / frame["SUBJECTS"].max())
            fig = go.Figure(go.Scatter3d(
                x=frame["RESOLUTION"], y=frame["QUALITY"], z=frame["DEVIATIONS"], mode="markers",
                text=frame["SITE_ID"].astype(str),
                hovertemplate="<b>%{text}</b><br>Resolution: %{x:.1f}%<br>Quality: %{y:.1f}"
                              "<br>Deviations: %{z:.0f}<extra></extra>",
                marker=dict(size=size, color=frame["QUALITY"], colorscale="Turbo", opacity=0.9,
                            colorbar=dict(title="Quality"), line=dict(width=0.5, color="rgba(255,255,255,.4)")),
            ))
            fig.update_layout(scene=dict(xaxis_title="Query resolution %", yaxis_title="Quality score",
                                         zaxis_title="Protocol deviations"))
            style_fig(fig, 580, "Sites in 3D: resolution x quality x deviations (size = subjects)")
            if auto:
                render_auto_rotating(fig, "lab_galaxy", 580)
            else:
                show_chart(fig, "lab_galaxy")

    queries = ctx.df("queries")
    status, priority = col_upper(queries, "QUERY_STATUS"), col_upper(queries, "PRIORITY")

    with t2:
        if status.eq("").all() or priority.eq("").all():
            notice("Needs QUERY_STATUS and PRIORITY columns in `queries.csv`.", "info")
        else:
            matrix = pd.crosstab(priority[priority.ne("")], status[status.ne("")])
            matrix = matrix.reindex(index=ordered(matrix.index, PRIORITY_ORDER),
                                    columns=ordered(matrix.columns, STATUS_ORDER), fill_value=0)
            show_chart(bars_3d(matrix, "Status", "Priority", "Queries: status x priority"), "lab_bars")

    with t3:
        if "SITE_ID" not in queries.columns or status.eq("").all():
            notice("Needs SITE_ID and QUERY_STATUS columns in `queries.csv`.", "info")
        else:
            sites_col = col_upper(queries, "SITE_ID")
            valid = sites_col.ne("") & status.ne("")
            grid = pd.crosstab(sites_col[valid], status[valid])
            grid = grid.loc[grid.sum(axis=1).sort_values(ascending=False).head(20).index]
            grid = grid.reindex(columns=ordered(grid.columns, STATUS_ORDER), fill_value=0)
            if grid.shape[0] < 2 or grid.shape[1] < 2:
                notice("Not enough sites/statuses to build a surface.", "info")
            else:
                fig = go.Figure(go.Surface(z=grid.to_numpy(), colorscale="Viridis",
                                           colorbar=dict(title="Queries"),
                                           contours=dict(z=dict(show=True, usecolormap=True, project_z=True))))
                fig.update_layout(scene=dict(
                    xaxis=dict(title="Status", tickvals=list(range(grid.shape[1])), ticktext=list(grid.columns)),
                    yaxis=dict(title="Site", tickvals=list(range(grid.shape[0])), ticktext=list(grid.index)),
                    zaxis=dict(title="Queries"),
                    camera=dict(eye=dict(x=1.8, y=-1.8, z=1.0)),
                ))
                show_chart(style_fig(fig, 580, "Query terrain: top 20 sites x status"), "lab_surface")

    with t4:
        date_col = find_column(queries, QUERY_DATE_COLUMNS)
        if not date_col:
            notice("Needs a query date column (e.g. CREATED_DATE) in `queries.csv`.", "info")
        else:
            long = _cumulative_by_month(queries, date_col)
            if long.empty or long["MONTH"].nunique() < 2:
                notice("Not enough dated queries for an animation.", "info")
            else:
                fig = px.bar(long, x="PRIORITY", y="CUMULATIVE", color="PRIORITY", animation_frame="MONTH",
                             color_discrete_map=PRIORITY_COLORS, range_y=[0, float(long["CUMULATIVE"].max()) * 1.15],
                             category_orders={"PRIORITY": list(PRIORITY_ORDER)})
                show_chart(style_fig(fig, 480, "Cumulative queries raised - press Play"), "lab_timeline")


def page_explorer(ctx: AppContext) -> None:
    st.subheader("🔍 Clinical Data Explorer")
    key = st.selectbox("Select dataset", EXPLORER_KEYS, format_func=lambda k: DATASET_REGISTRY[k][2], key="explorer_pick")
    df = ctx.df(key)
    if df.empty:
        notice("Selected dataset is empty or unavailable.")
        return

    label = DATASET_REGISTRY[key][2]
    c1, c2, c3 = st.columns(3)
    c1.metric("Records", fmt_int(len(df)))
    c2.metric("Columns", fmt_int(len(df.columns)))
    c3.metric("Missing cells", fmt_int(df.isna().sum().sum()))

    picked = st.multiselect("Columns to show (blank = all)", list(df.columns), key=f"explorer_cols_{key}")
    view = df[picked] if picked else df
    view = filter_table(view, f"explorer_{key}")
    show_df(view, height=560)
    st.download_button("⬇️ Download CSV", data=view.to_csv(index=False).encode("utf-8"),
                       file_name=f"{label.lower().replace(' ', '_')}.csv", mime="text/csv",
                       key=f"download_{key}")


PAGES: dict[str, Callable[[AppContext], None]] = {
    "📊 Executive Dashboard": page_executive,
    "📁 Data Overview": page_overview,
    "🔎 Data Quality": page_quality,
    "📨 Query Management": page_queries,
    "🏥 Site Performance": page_sites,
    "⚠️ Protocol Deviations": page_deviations,
    "🔒 Database Lock": page_lock,
    "📋 Validation Rules": page_rules,
    "🧊 3D Lab": page_3d_lab,
    "🔍 Data Explorer": page_explorer,
}


# ============================================================
# MAIN
# ============================================================

def main() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    # Sidebar containers keep a fixed visual order while widgets are created out of order.
    st.sidebar.title("🧬 CDM Quality System")
    st.sidebar.caption("Data → Cleaning → Validation → Queries → Quality → Lock")
    nav_box = st.sidebar.container()
    filter_box = st.sidebar.container()
    source_box = st.sidebar.container()

    with source_box:
        st.divider()
        force_demo = st.toggle("Use demo data", value=False, key="force_demo",
                               help="Show a synthetic dataset instead of the CSV files.")
        if st.button("🔄 Reload data", key="reload", help="Clear caches and re-read the CSV files."):
            st.cache_data.clear()
            st.rerun()

    try:
        bundle = load_data(force_demo=force_demo)
    except Exception as exc:  # noqa: BLE001 - last-resort guard so the app never white-screens
        LOGGER.exception("Data load failed")
        st.error(f"Data loading failed: {exc}. Showing demo data instead.")
        bundle = DataBundle(build_demo_data(), is_demo=True)

    with source_box:
        with st.expander("🩺 Data health", expanded=False):
            if not bundle.messages:
                st.success("All files loaded.")
            for level, text in bundle.messages:
                notice(text, level)
        st.caption("Automated Quality Monitoring")

    with filter_box:
        st.divider()
        selected_sites = st.multiselect("Site filter (blank = all)", collect_site_ids(bundle.frames), key="site_filter")

    with nav_box:
        page = st.radio("Navigate", list(PAGES), label_visibility="collapsed", key="nav")

    frames = apply_site_filter(bundle.frames, selected_sites)
    kpis = compute_kpis(frames)
    gates = evaluate_gates(kpis)
    status, score = lock_state(kpis, gates)
    ctx = AppContext(frames, kpis, gates, status, score, bundle.is_demo)

    render_hero(bundle.is_demo)
    if selected_sites:
        st.info(f"Filtered to {len(selected_sites)} site(s): {', '.join(selected_sites[:6])}"
                f"{' ...' if len(selected_sites) > 6 else ''}")

    try:
        PAGES[page](ctx)
    except Exception as exc:  # noqa: BLE001 - isolate page failures
        LOGGER.exception("Page '%s' failed", page)
        st.error(f"This page hit an unexpected problem: {exc}")
        with st.expander("Technical details"):
            st.exception(exc)

    st.divider()
    st.caption("Clinical Trial CDM Quality System | Data Quality • Query Management • "
               "Site Performance • Database Lock Readiness")


main()
