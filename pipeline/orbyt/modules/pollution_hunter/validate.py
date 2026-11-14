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
from orbyt.sources import campd, era5

HOURS_BEFORE = 3
HOURS_PER_YEAR = 8766.0  # 365.25 days
LOG_MIN_SHARE = 0.01
# Axis range of the figures, t NOx per year. Estimates below the bottom are drawn on the edge.
AX_MIN, AX_MAX = 1_000.0, 200_000.0
OUT_DIR = Path(__file__).resolve().parents[4] / "docs" / "validation"
# Footprints where the sum of CEMS monitors may miss large non-power-plant NOx next door.
# Named by Badr from his own knowledge of the sites, not found by the pipeline.
UNMONITORED_INDUSTRY = ("Midland", "Sabine", "R S Nelson", "W A Parish")


def is_flagged(name: str) -> bool:
    return any(name.startswith(n) for n in UNMONITORED_INDUSTRY)


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


def estimate_row(
    entry: dict, year: int, level: str, out_dir: Path, hourly: Path, annual: Path, con
) -> dict[str, Any]:
    sid = entry["subject_id"]
    row: dict[str, Any] = {
        "subject_id": sid,
        "name": entry["name"],
        "state": entry["county_state"],
        "tier": entry["tier"],
        "year": year,
        "level": level,
        "n_plants": entry["n_plants"],
        "measured_share": entry["measured_share"],
        "flag_unmonitored_industry": is_flagged(entry["name"]),
        "est_t_yr": None,
        "lo": None,
        "hi": None,
        "gates_failed": None,
        "days_used": None,
        "v1_ref_t_yr": None,
        "v2_ref_t_yr": annual_reference(annual, entry["plant_ids_eia"], year),
    }
    path = out_dir / sid / observe.estimate_name(year, level=level)
    if not path.exists():
        return row
    doc = json.loads(path.read_text(encoding="utf-8"))
    obs = doc["observed"]
    row["gates_failed"] = ",".join(doc["gates_failed"])
    row["days_used"] = doc["days"]["used"]
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
    return row


def passed(row: dict) -> bool:
    return row["est_t_yr"] is not None and row["gates_failed"] == ""


def summarise(rows: list[dict]) -> list[dict]:
    """One line per level, comparison, tier group and gate filter."""
    out = []
    groups = {"tier 1": {1}, "tier 2": {2}, "pooled": {1, 2}}
    for level in sorted({r["level"] for r in rows}):
        for comp, key in (("V1", "v1_ref_t_yr"), ("V2", "v2_ref_t_yr")):
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


def summary_markdown(summary: list[dict], rows: list[dict]) -> str:
    lines = [
        "# Validation against US stack monitors (M4.3)",
        "",
        "Pass marks (PLAN.md 4.9, V1): mean bias within 20 percent and correlation above 0.7.",
        "Bias is the ratio of sums minus one. Scatter is the standard deviation of ln(estimate / "
        "monitor).",
        "",
    ]
    for level in sorted({s["level"] for s in summary}):
        for comp in ("V1", "V2"):
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
    flagged = sorted({r["name"] for r in rows if r["flag_unmonitored_industry"]})
    lines += [
        "## Flagged for possible unmonitored industry",
        "",
        "The monitor total is the sum of CEMS power plants. Refineries, chemical plants and other "
        "industry beside these plants report nothing to CEMS, so a satellite estimate above the "
        "monitors may be real emissions that the monitors cannot see: " + ", ".join(flagged) + ".",
        "",
    ]
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
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, (title, key) in zip(
        axes,
        (("V1 like for like (3 h before overpass)", "v1_ref_t_yr"), ("V2 annual", "v2_ref_t_yr")),
        strict=True,
    ):
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
        ax.set_xlabel("monitors (CEMS), t NOx per year")
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
    con = duckdb.connect()
    rows = [
        estimate_row(e, y, lv, args.in_dir, hourly, annual, con)
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
    (args.out / "validation_summary.md").write_text(summary_markdown(summary, rows), "utf-8")
    for lv in args.levels:
        draw_figure(rows, lv, args.out / f"validation_{lv}.png")
    print(f"wrote {len(rows)} rows and figures to {args.out}")


if __name__ == "__main__":
    main()
