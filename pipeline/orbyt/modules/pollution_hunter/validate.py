"""M4.3: compare the satellite estimates with US stack monitors (PLAN.md 4.9, V1 and V2).

    uv run python -m orbyt.modules.pollution_hunter.validate --years 2023 2024 --levels 100m 500m

For every validation footprint, year and wind level, with an estimate from observe.py:

V1  like for like. The monitor NOx of the footprint, averaged over the three whole UTC hours that
    end at the start of the hour of the overpass, on the days the estimate used, as tonnes per
    year. The CEMS hour is the hour that starts at ``hour_utc``, so a pass at 18:42 UTC is
    compared with the hours starting 15:00, 16:00 and 17:00. An hour with no CEMS record is a
    plant that was off, and counts as zero.
V2  annual. The same estimate against the calendar-year monitor total of the footprint. This
    includes the error from seeing only clear, windy middays.

Statistics are computed for tier 1, tier 2 and both pooled, for all footprints and for the ones
whose estimate passed every gate. The monitor total is the sum over the plants of the footprint.
Nothing here changes the method or its constants.

M4.4 adds the footprint reference (V1f, V2f): the monitor total plus the NOx that the monitors
cannot see, from the EPA 2023 National Emissions Inventory (sources/nei.py): every non-power
facility within the footprint radius, plus NEI power plants above the CEMS total. This is the
footprint accounting of PLAN.md 4.5, the same as the European comparison, where the register
holds industry as well as power plants. A footprint is flagged when that unmonitored NOx is at
least ``validation.nei.flag_frac`` of the monitor total.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from orbyt.modules.pollution_hunter import extract, observe, validation_set
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import campd, era5, nei

HOURS_BEFORE = 3
HOURS_PER_YEAR = 8766.0  # 365.25 days
LOG_MIN_SHARE = 0.01
# Axis range of the figures, t NOx per year. Estimates below the bottom are drawn on the edge.
AX_MIN, AX_MAX = 1_000.0, 200_000.0
OUT_DIR = Path(__file__).resolve().parents[4] / "docs" / "validation"
# Comparison name, reference column, and what the reference is.
COMPARISONS = (
    ("V1", "v1_ref_t_yr", "monitors, 3 h before each pass"),
    ("V2", "v2_ref_t_yr", "monitors, calendar year"),
    ("V1f", "v1_fp_ref_t_yr", "footprint (monitors + NEI unmonitored), 3 h before each pass"),
    ("V2f", "v2_fp_ref_t_yr", "footprint (monitors + NEI unmonitored), calendar year"),
)
# Footprint size classes for the pass-rate table, t NOx per year (monitors + NEI unmonitored).
SIZE_CLASSES = ((0.0, 4000.0), (4000.0, 6000.0), (6000.0, math.inf))
GATES = (
    "too_few_days",
    "poor_fit",
    "source_offset",
    "lifetime_out_of_range",
    "low_signal_to_noise",
)


def is_flagged(unmonitored_t: float | None, monitor_t: float | None, frac: float) -> bool:
    """True when the NOx the monitors miss is at least ``frac`` of what they see."""
    if unmonitored_t is None or not monitor_t:
        return False
    return unmonitored_t >= frac * monitor_t


def _naive(moment: datetime) -> datetime:
    return moment.astimezone(UTC).replace(tzinfo=None) if moment.tzinfo else moment


def hourly_series(con: duckdb.DuckDBPyConnection, hourly: Path, plant_ids: list[int]) -> dict:
    """{hour start (naive UTC): kg NOx as NO2} summed over the plants of a footprint."""
    path = str(hourly).replace("\\", "/")
    ids = ",".join(str(int(i)) for i in plant_ids)
    rows = con.execute(
        f"""
        select hour_utc, sum(nox_mass_lbs) * {campd.LB_TO_KG}
        from read_parquet('{path}') where plant_id_eia in ({ids}) and nox_mass_lbs is not null
        group by hour_utc
        """
    ).fetchall()
    return {_naive(h): float(kg) for h, kg in rows}


def like_for_like(
    series: dict[datetime, float], pass_times: list[datetime], hours_before: int = HOURS_BEFORE
) -> float | None:
    """Mean monitor rate over the ``hours_before`` whole hours before each pass, in t/yr."""
    rates = []
    for t in pass_times:
        top = _naive(t).replace(minute=0, second=0, microsecond=0)
        hrs = [top - timedelta(hours=k) for k in range(1, hours_before + 1)]
        rates.append(sum(series.get(h, 0.0) for h in hrs) / hours_before)
    if not rates:
        return None
    return float(np.mean(rates)) * HOURS_PER_YEAR / 1000.0


def annual_reference(annual: Path, plant_ids: list[int], year: int) -> float | None:
    ids = ",".join(str(int(i)) for i in plant_ids)
    path = str(annual).replace("\\", "/")
    row = (
        duckdb.connect()
        .execute(
            f"select sum(nox_t) from read_parquet('{path}') "
            f"where year = {int(year)} and plant_id_eia in ({ids})"
        )
        .fetchone()
    )
    return None if row is None or row[0] is None else float(row[0])


def _ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="stable")
    ranks = np.empty(len(x))
    ranks[order] = np.arange(len(x))
    return ranks


def compare_stats(est: list[float], ref: list[float]) -> dict[str, Any]:
    """Bias, correlation and scatter of estimates against a reference, same units."""
    e, r = np.asarray(est, dtype=float), np.asarray(ref, dtype=float)
    ok = np.isfinite(e) & np.isfinite(r) & (e >= 0) & (r > 0)
    e, r = e[ok], r[ok]
    n = len(e)
    out: dict[str, Any] = {"n": n}
    if n == 0:
        return out
    out["bias_pct"] = 100.0 * (e.sum() / r.sum() - 1.0)
    out["median_ratio"] = float(np.median(e / r))
    if n >= 3 and e.std() > 0 and r.std() > 0:
        out["pearson"] = float(np.corrcoef(e, r)[0, 1])
        out["spearman"] = float(np.corrcoef(_ranks(e), _ranks(r))[0, 1])
        # A log ratio needs an estimate that is not zero. Estimates under 1 percent of the monitor
        # (no plume found) count in the bias and the correlation, and are counted here, not logged.
        keep = e >= LOG_MIN_SHARE * r
        out["n_no_plume"] = int((~keep).sum())
        if keep.sum() >= 3:
            out["log_scatter"] = float(np.std(np.log(e[keep] / r[keep]), ddof=1))
    return out


def boot_log_sd(lo: float | None, hi: float | None) -> float | None:
    """The bootstrap interval as one log standard deviation, as in PLAN.md 4.8 (s_boot)."""
    if lo is None or hi is None or not (lo > 0 and hi > lo):
        return None
    return (math.log(hi) - math.log(lo)) / 3.92


def systematic_scatter(rows: list[dict], key: str) -> dict[str, Any]:
    """Scatter of ln(estimate / reference) beyond what the bootstrap explains (u_sys, 4.8).

    ``observed`` is the standard deviation of the log ratio, ``boot`` the root mean square of
    each estimate's s_boot, ``excess`` the square root of the difference (never below zero).
    The verdict rule adds u_sys to each estimate's own s_boot, so the excess is what u_sys
    stands for. ``upper95`` is the one-sided 95% upper bound of ``observed`` from the chi-square
    distribution, to show how little a handful of points pins it down.
    """
    pairs = [
        (r["est_t_yr"] / r[key], boot_log_sd(r["lo"], r["hi"]))
        for r in rows
        if r["est_t_yr"] and r.get(key) and r["est_t_yr"] >= LOG_MIN_SHARE * r[key]
    ]
    pairs = [(x, s) for x, s in pairs if s is not None]
    n = len(pairs)
    if n < 3:
        return {"n": n}
    from scipy.stats import chi2

    lr = np.log([x for x, _ in pairs])
    sb2 = float(np.mean([s * s for _, s in pairs]))
    var = float(np.var(lr, ddof=1))
    return {
        "n": n,
        "mean_log_ratio": float(lr.mean()),
        "observed": math.sqrt(var),
        "boot": math.sqrt(sb2),
        "excess": math.sqrt(max(0.0, var - sb2)),
        "upper95": math.sqrt(var * (n - 1) / chi2.ppf(0.05, n - 1)),
    }


def nei_by_subject(entries: list[dict], radius_km: float) -> dict[str, dict]:
    """Unmonitored NOx per footprint, against the CEMS total of the inventory year."""
    fac = nei.load_facilities(nei.fetch())
    return {
        e["subject_id"]: nei.footprint(
            fac, e["lat"], e["lon"], radius_km, float(e[f"nox_t_{nei.NEI_YEAR}"])
        )
        for e in entries
    }


def estimate_row(
    entry: dict,
    year: int,
    level: str,
    out_dir: Path,
    hourly: Path,
    annual: Path,
    con,
    nei_fp: dict | None = None,
    flag_frac: float = 0.25,
) -> dict[str, Any]:
    sid = entry["subject_id"]
    v2 = annual_reference(annual, entry["plant_ids_eia"], year)
    unmon = None if nei_fp is None else nei_fp["unmonitored_t"]
    row: dict[str, Any] = {
        "subject_id": sid,
        "name": entry["name"],
        "state": entry["county_state"],
        "tier": entry["tier"],
        "year": year,
        "level": level,
        "n_plants": entry["n_plants"],
        "measured_share": entry["measured_share"],
        "nei_unmonitored_t_yr": unmon,
        "nei_largest": ""
        if nei_fp is None
        else "; ".join(
            [f"{f['name']} {f['nox_t']:.0f} t" for f in nei_fp["largest"] if f["nox_t"] >= 100]
            + (
                [f"NEI power plants above CEMS {nei_fp['power_gap_t']:.0f} t"]
                if nei_fp["power_gap_t"] >= 100
                else []
            )
        ),
        "flag_unmonitored_industry": is_flagged(unmon, v2, flag_frac),
        "est_t_yr": None,
        "lo": None,
        "hi": None,
        "gates_failed": None,
        "days_used": None,
        "v1_ref_t_yr": None,
        "v2_ref_t_yr": v2,
        "v1_fp_ref_t_yr": None,
        "v2_fp_ref_t_yr": None if v2 is None or unmon is None else v2 + unmon,
        "mean_wind_ms": None,
    }
    path = out_dir / sid / observe.estimate_name(year, level=level)
    if not path.exists():
        return row
    doc = json.loads(path.read_text(encoding="utf-8"))
    obs = doc["observed"]
    row["gates_failed"] = ",".join(doc["gates_failed"])
    row["days_used"] = doc["days"]["used"]
    speeds = [d["wind_ms"] for d in doc["day_list"] if d.get("wind_ms") is not None]
    row["mean_wind_ms"] = float(np.mean(speeds)) if speeds else None
    if obs is not None:
        row["est_t_yr"], row["lo"], row["hi"] = obs["nox_t_yr"], obs["lo"], obs["hi"]
    wind = era5.read_winds(era5.wind_path(out_dir, sid, level))
    used = {d["date"] for d in doc["day_list"]}
    passes = [
        datetime.fromisoformat(w.pass_utc.replace("Z", "+00:00"))
        for w in wind
        if w.day in used and w.day.startswith(f"{year}-")
    ]
    series = hourly_series(con, hourly, entry["plant_ids_eia"])
    row["v1_ref_t_yr"] = like_for_like(series, passes)
    # The inventory is annual, so the unmonitored part enters V1 as a flat rate.
    if row["v1_ref_t_yr"] is not None and unmon is not None:
        row["v1_fp_ref_t_yr"] = row["v1_ref_t_yr"] + unmon
    return row


def passed(row: dict) -> bool:
    return row["est_t_yr"] is not None and row["gates_failed"] == ""


def summarise(rows: list[dict]) -> list[dict]:
    """One line per level, comparison, tier group and gate filter."""
    out = []
    groups = {"tier 1": {1}, "tier 2": {2}, "pooled": {1, 2}}
    for level in sorted({r["level"] for r in rows}):
        for comp, key, _ in COMPARISONS:
            if not any(r.get(key) for r in rows):
                continue
            for gname, tiers in groups.items():
                for filt in ("all", "gates passed"):
                    sel = [
                        r
                        for r in rows
                        if r["level"] == level
                        and r["tier"] in tiers
                        and r["est_t_yr"] is not None
                        and (filt == "all" or passed(r))
                    ]
                    stats = compare_stats([r["est_t_yr"] for r in sel], [r[key] for r in sel])
                    out.append(
                        {
                            "level": level,
                            "comparison": comp,
                            "group": gname,
                            "subset": filt,
                            **stats,
                        }
                    )
    return out


def _fmt(x: Any, nd: int = 2) -> str:
    return "" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def gate_counts(rows: list[dict], level: str) -> list[dict]:
    """Per tier: estimates, passes, and how often each gate fails (alone and in all)."""
    out = []
    for tier in sorted({r["tier"] for r in rows}):
        sel = [
            r
            for r in rows
            if r["level"] == level and r["tier"] == tier and r["gates_failed"] is not None
        ]
        fails = [[g for g in r["gates_failed"].split(",") if g] for r in sel]
        line: dict[str, Any] = {"tier": tier, "n": len(sel), "passed": sum(not f for f in fails)}
        for g in GATES:
            line[g] = sum(g in f for f in fails)
            line[g + "_alone"] = sum(f == [g] for f in fails)
        out.append(line)
    return out


def pass_by_size(rows: list[dict], level: str) -> list[dict]:
    """Pass rate by footprint size (calendar-year footprint reference), per tier."""
    out = []
    for lo, hi in SIZE_CLASSES:
        for tier in sorted({r["tier"] for r in rows}):
            sel = [
                r
                for r in rows
                if r["level"] == level
                and r["tier"] == tier
                and r["gates_failed"] is not None
                and r.get("v2_fp_ref_t_yr") is not None
                and lo <= r["v2_fp_ref_t_yr"] < hi
            ]
            out.append(
                {
                    "lo": lo,
                    "hi": hi,
                    "tier": tier,
                    "n": len(sel),
                    "passed": sum(passed(r) for r in sel),
                }
            )
    return out


def _log_stats(pairs: list[tuple[float, float]]) -> dict[str, float]:
    """Geometric mean ratio, its standard error in log units, log scatter and Pearson r."""
    est = np.array([e for e, _ in pairs], dtype=float)
    ref = np.array([r for _, r in pairs], dtype=float)
    lr = np.log(est / ref)
    n = len(lr)
    sd = float(lr.std(ddof=1)) if n > 1 else math.nan
    return {
        "n": n,
        "geo": float(math.exp(lr.mean())) if n else math.nan,
        "se": sd / math.sqrt(n) if n > 1 else math.nan,
        "scatter": sd,
        "r": float(np.corrcoef(est, ref)[0, 1]) if n > 2 else math.nan,
    }


def level_comparison(rows: list[dict], base: str = "100m", alt: str = "500m") -> list[str]:
    """Markdown comparing two wind levels estimate by estimate (M4.4, PLAN.md 4.3 step 3).

    Each estimate is set against its own reference (V1 uses the days that level kept). An
    estimate under 1% of its monitors (no plume) is left out, as in the log scatter above.
    """
    by: dict[tuple[str, int], dict[str, dict]] = {}
    for r in rows:
        by.setdefault((r["subject_id"], r["year"]), {})[r["level"]] = r
    pairs = [(d[base], d[alt]) for d in by.values() if base in d and alt in d]

    def plume(r: dict) -> bool:
        return (
            r["est_t_yr"] is not None
            and bool(r["v1_ref_t_yr"])
            and r["est_t_yr"] > 0.01 * r["v1_ref_t_yr"]
        )

    both = [(a, b) for a, b in pairs if plume(a) and plume(b)]
    if not both:
        return []
    wr = np.array(
        [b["mean_wind_ms"] / a["mean_wind_ms"] for a, b in both if a["mean_wind_ms"]],
        dtype=float,
    )
    er = np.array([b["est_t_yr"] / a["est_t_yr"] for a, b in both])
    moved = float(np.mean(np.abs(np.log(er)) > math.log(1.15)))
    lines = [
        f"## Wind {base} against {alt}",
        "",
        f"{len(both)} estimates find a plume at both levels. Mean wind over the days used, "
        f"{alt} / {base}: median {np.median(wr):.2f}, range {wr.min():.2f} to {wr.max():.2f}. "
        f"Estimate {alt} / {base}: median {np.median(er):.2f}, geometric mean "
        f"{math.exp(np.log(er).mean()):.2f}; {moved:.0%} move by more than 15% (V4 pass mark).",
        "",
        "Passing every gate at each level:",
        "",
        f"| tier | both | {base} only | {alt} only | neither |",
        "|---|---|---|---|---|",
    ]
    for tier in (1, 2):
        t = [(passed(a), passed(b)) for a, b in pairs if a["tier"] == tier]
        lines.append(
            f"| {tier} | {sum(x and y for x, y in t)} | {sum(x and not y for x, y in t)} "
            f"| {sum(y and not x for x, y in t)} | {sum(not x and not y for x, y in t)} |"
        )

    def fit_ok(r: dict) -> bool:
        g = r["gates_failed"] or ""
        return "poor_fit" not in g and "source_offset" not in g

    sets = [
        (
            "passes at both, tier 1",
            [(a, b) for a, b in pairs if a["tier"] == 1 and passed(a) and passed(b)],
        ),
        ("passes at both, pooled", [(a, b) for a, b in pairs if passed(a) and passed(b)]),
        (
            "fit and plume start pass at both, tier 1",
            [(a, b) for a, b in both if a["tier"] == 1 and fit_ok(a) and fit_ok(b)],
        ),
    ]
    lines += [
        "",
        "Geometric mean ratio (standard error in log units), log scatter and Pearson r, on the "
        "same estimates at both levels, and on each level's own set of estimates that pass "
        "every gate:",
        "",
        f"| set | reference | n | {base} ratio (se) | scatter | r | {alt} ratio (se) | scatter "
        "| r |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    def cells(s: dict[str, float]) -> str:
        return f"{s['geo']:.2f} ({s['se']:.2f}) | {s['scatter']:.2f} | {_fmt(s['r'])}"

    for comp, key, _ in COMPARISONS:
        if comp not in ("V1", "V1f", "V2f"):
            continue
        for name, sel in sets:
            sel = [(a, b) for a, b in sel if a[key] and b[key]]
            if len(sel) < 3:
                continue
            sa = _log_stats([(a["est_t_yr"], a[key]) for a, _ in sel])
            sb = _log_stats([(b["est_t_yr"], b[key]) for _, b in sel])
            lines.append(f"| {name} | {comp} | {len(sel)} | {cells(sa)} | {cells(sb)} |")
        for gname, tiers in (("own gated set, tier 1", {1}), ("own gated set, pooled", {1, 2})):
            ga = [a for a, _ in pairs if a["tier"] in tiers and passed(a) and a[key]]
            gb = [b for _, b in pairs if b["tier"] in tiers and passed(b) and b[key]]
            sa = _log_stats([(r["est_t_yr"], r[key]) for r in ga])
            sb = _log_stats([(r["est_t_yr"], r[key]) for r in gb])
            lines.append(
                f"| {gname} | {comp} | {len(ga)} and {len(gb)} | {cells(sa)} | {cells(sb)} |"
            )
    lines.append("")
    return lines


def summary_markdown(summary: list[dict], rows: list[dict], flag_frac: float = 0.25) -> str:
    lines = [
        "# Validation against US stack monitors (M4.3, M4.4)",
        "",
        "Pass marks (PLAN.md 4.9, V1): mean bias within 20 percent and correlation above 0.7.",
        "Bias is the ratio of sums minus one. Scatter is the standard deviation of ln(estimate / "
        "reference).",
        "",
        "References: " + "; ".join(f"{c} {d}" for c, _, d in COMPARISONS) + ". The unmonitored "
        f"NOx is from {getattr(nei, 'SOURCE', 'the NEI')}, used for both years.",
        "",
    ]
    for level in sorted({s["level"] for s in summary}):
        lines += [
            f"## Gates, wind {level}",
            "",
            "Times each gate failed, in all and alone (the only gate that failed).",
            "",
            "| tier | n | passed | " + " | ".join(GATES) + " |",
            "|---|---|---|" + "---|" * len(GATES),
        ]
        for g in gate_counts(rows, level):
            lines.append(
                f"| {g['tier']} | {g['n']} | {g['passed']} | "
                + " | ".join(f"{g[k]} ({g[k + '_alone']})" for k in GATES)
                + " |"
            )
        lines += [
            "",
            "Passes by footprint size (calendar-year monitors + NEI unmonitored):",
            "",
            "| footprint t/yr | tier | n | passed |",
            "|---|---|---|---|",
        ]
        for s in pass_by_size(rows, level):
            size = (
                f"{s['lo']:,.0f}+" if math.isinf(s["hi"]) else f"{s['lo']:,.0f} to {s['hi']:,.0f}"
            )
            lines.append(f"| {size} | {s['tier']} | {s['n']} | {s['passed']} |")
        lines += [
            "",
            "Systematic scatter of the estimates that pass every gate (u_sys, PLAN.md "
            "4.8): observed log scatter, the part the bootstrap explains, the excess, and the "
            "one-sided 95% upper bound of the observed scatter.",
            "",
            "| comparison | group | n | mean ratio | observed | bootstrap | excess | upper 95% |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for comp, key, _ in COMPARISONS:
            for gname, tiers in (("tier 1", {1}), ("pooled", {1, 2})):
                sel = [r for r in rows if r["level"] == level and r["tier"] in tiers and passed(r)]
                s = systematic_scatter(sel, key)
                if s["n"] < 3:
                    continue
                lines.append(
                    f"| {comp} | {gname} | {s['n']} | {math.exp(s['mean_log_ratio']):.2f} "
                    f"| {s['observed']:.2f} | {s['boot']:.2f} | {s['excess']:.2f} "
                    f"| {s['upper95']:.2f} |"
                )
        lines.append("")
    lines += level_comparison(rows)
    for level in sorted({s["level"] for s in summary}):
        for comp, _, _ in COMPARISONS:
            if not any(s["comparison"] == comp and s["level"] == level for s in summary):
                continue
            lines += [
                f"## {comp}, wind {level}",
                "",
                "| group | subset | n | bias % | median ratio | Pearson r | Spearman r "
                "| log scatter | no plume |",
                "|---|---|---|---|---|---|---|---|---|",
            ]
            for s in summary:
                if s["level"] == level and s["comparison"] == comp:
                    lines.append(
                        f"| {s['group']} | {s['subset']} | {s['n']} | {_fmt(s.get('bias_pct'), 0)} "
                        f"| {_fmt(s.get('median_ratio'))} | {_fmt(s.get('pearson'))} "
                        f"| {_fmt(s.get('spearman'))} | {_fmt(s.get('log_scatter'))} "
                        f"| {s.get('n_no_plume', '')} |"
                    )
            lines.append("")
    lines += [
        "## Footprints with unmonitored NOx",
        "",
        "The monitor total is the sum of CEMS power plants. Refineries, chemical plants and other "
        "industry report nothing to CEMS. A footprint is flagged when the NEI lists unmonitored "
        f"NOx of at least {flag_frac:.0%} of the monitor total within the footprint.",
        "",
        "| footprint | tier | monitors 2023 t | NEI unmonitored t | largest sources |",
        "|---|---|---|---|---|",
    ]
    seen = set()
    for r in rows:
        if r["flag_unmonitored_industry"] and r["subject_id"] not in seen and r["year"] == 2023:
            seen.add(r["subject_id"])
            lines.append(
                f"| {r['name']} | {r['tier']} | {r['v2_ref_t_yr']:,.0f} "
                f"| {r['nei_unmonitored_t_yr']:,.0f} | {r['nei_largest']} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_table(rows: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def draw_figure(rows: list[dict], level: str, path: Path) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {1: "#1f5fa8", 2: "#d9822b"}
    panels = [
        ("V1 like for like (3 h before overpass)", "v1_ref_t_yr", "monitors (CEMS)"),
        ("V2 annual", "v2_ref_t_yr", "monitors (CEMS)"),
    ]
    if any(r.get("v2_fp_ref_t_yr") for r in rows):
        panels.append(("V2f annual, whole footprint", "v2_fp_ref_t_yr", "CEMS + NEI unmonitored"))
    fig, axes = plt.subplots(1, len(panels), figsize=(5.5 * len(panels), 5.2))
    for ax, (title, key, xlabel) in zip(axes, panels, strict=True):
        sel = [r for r in rows if r["level"] == level and r["est_t_yr"] is not None and r[key]]
        for r in sel:
            ok = passed(r)
            # An estimate under the bottom of the axis (no plume found) sits on the bottom edge.
            below = r["est_t_yr"] < AX_MIN
            y = max(r["est_t_yr"], AX_MIN)
            lo = min(max(r["lo"], AX_MIN), y)
            hi = max(r["hi"], y)
            ax.errorbar(
                r[key],
                y,
                yerr=[[y - lo], [hi - y]],
                fmt="v" if below else ("o" if ok else "s"),
                ms=6,
                color=colors[r["tier"]],
                mfc=colors[r["tier"]] if ok else "white",
                ecolor=colors[r["tier"]],
                elinewidth=0.8,
                alpha=0.85,
            )
            if r["flag_unmonitored_industry"]:
                ax.annotate(
                    r["name"].split()[0] + " " + str(r["year"])[2:],
                    (r[key], y),
                    fontsize=7,
                    xytext=(4, 4),
                    textcoords="offset points",
                )
        ax.plot([AX_MIN, AX_MAX], [AX_MIN, AX_MAX], color="0.4", lw=1)
        ax.plot([AX_MIN, AX_MAX], [AX_MIN * 0.8, AX_MAX * 0.8], color="0.7", lw=0.8, ls="--")
        ax.plot([AX_MIN, AX_MAX], [AX_MIN * 1.2, AX_MAX * 1.2], color="0.7", lw=0.8, ls="--")
        ax.set_xlim(AX_MIN, AX_MAX)
        ax.set_ylim(AX_MIN, AX_MAX)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlabel(f"{xlabel}, t NOx per year")
        ax.set_ylabel("satellite estimate, t NOx per year")
        ax.set_title(title, fontsize=10)
        ax.set_aspect("equal", adjustable="box")
    handles = [
        plt.Line2D([], [], marker="o", ls="", color=colors[1], label="tier 1"),
        plt.Line2D([], [], marker="o", ls="", color=colors[2], label="tier 2"),
        plt.Line2D([], [], marker="s", ls="", mfc="white", color="0.3", label="a gate failed"),
        plt.Line2D([], [], marker="v", ls="", color="0.3", label="under 1,000 t/yr (no plume)"),
    ]
    axes[0].legend(handles=handles, loc="upper left", fontsize=8, frameon=False)
    fig.suptitle(f"Satellite estimates against US stack monitors, wind {level}", fontsize=11)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the estimates against CEMS monitors")
    parser.add_argument("--years", type=int, nargs="+", default=[2023, 2024])
    parser.add_argument("--levels", nargs="+", default=["100m", "500m"])
    parser.add_argument("--in-dir", type=Path, default=extract.INTERIM_DIR)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args()
    entries = json.loads(validation_set.PLANTS_JSON.read_text(encoding="utf-8"))
    hourly = campd.hourly_path()
    annual = campd.WAREHOUSE_DIR / "campd_annual.parquet"
    cfg = load_config()
    flag_frac = cfg["validation"]["nei"]["flag_frac"]
    nei_fp = nei_by_subject(entries, cfg["candidates"]["footprint_km"])
    con = duckdb.connect()
    rows = [
        estimate_row(e, y, lv, args.in_dir, hourly, annual, con, nei_fp[e["subject_id"]], flag_frac)
        for lv in args.levels
        for y in args.years
        for e in entries
    ]
    rows = [r for r in rows if r["est_t_yr"] is not None or r["gates_failed"] is not None]
    if not rows:
        raise SystemExit("no estimates found")
    write_table(rows, args.out / "validation_table.csv")
    summary = summarise(rows)
    write_table(summary, args.out / "validation_summary.csv")
    (args.out / "validation_summary.md").write_text(
        summary_markdown(summary, rows, flag_frac), "utf-8"
    )
    for lv in sorted({r["level"] for r in rows}):
        draw_figure(rows, lv, args.out / f"validation_{lv}.png")
    print(f"wrote {len(rows)} rows and figures to {args.out}")


if __name__ == "__main__":
    main()
