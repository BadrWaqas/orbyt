"""M4.5: summarise the null test (PLAN.md 4.9, V3).

    uv run python -m orbyt.modules.pollution_hunter.null_report

Reads ``null_sites.json`` and each site's 2024 estimate at the wind level the estimates use
(``--level 100m`` for the M4.5 run), and writes
``docs/validation/null_test.md`` and ``null_test.csv``. The pass mark is that no site passes
every gate. A site that does is a false positive and needs a manual look.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from orbyt.modules.pollution_hunter import extract, null_sites, observe
from orbyt.modules.pollution_hunter.config import wind_level

OUT_DIR = Path(__file__).resolve().parents[4] / "docs" / "validation"
GATES = (
    "too_few_days",
    "poor_fit",
    "source_offset",
    "lifetime_out_of_range",
    "low_signal_to_noise",
)


def site_row(
    site: dict[str, Any], year: int, out_dir: Path, level: str | None = None
) -> dict[str, Any]:
    path = out_dir / site["subject_id"] / observe.estimate_name(year, level=level)
    row: dict[str, Any] = {
        "subject_id": site["subject_id"],
        "name": site["name"],
        "region": site["region"],
        "stratum": site["stratum"],
        "nearest_big_city": site["nearest_big_city"],
        "days_used": None,
        "est_t_yr": None,
        "gates_failed": None,
        "n_gates_failed": None,
        "passes_all_gates": None,
    }
    if not path.exists():
        return row
    doc = json.loads(path.read_text(encoding="utf-8"))
    failed = doc["gates_failed"]
    row["days_used"] = doc["days"]["used"]
    row["est_t_yr"] = None if doc["observed"] is None else doc["observed"]["nox_t_yr"]
    row["gates_failed"] = ",".join(failed)
    row["n_gates_failed"] = len(failed)
    row["passes_all_gates"] = not failed and doc["observed"] is not None
    return row


def gate_counts(rows: list[dict]) -> dict[str, int]:
    counts = dict.fromkeys(GATES, 0)
    for r in rows:
        for g in (r["gates_failed"] or "").split(","):
            if g in counts:
                counts[g] += 1
    return counts


def report_markdown(rows: list[dict], year: int, level: str | None = None) -> str:
    level = level or wind_level()
    done = [r for r in rows if r["gates_failed"] is not None]
    passing = [r for r in done if r["passes_all_gates"]]
    lines = [
        "# Null test at 20 empty sites (M4.5, PLAN.md 4.9 V3)",
        "",
        f"Estimates for {year}, {level.removesuffix('m')} m wind, the same pipeline and gates as "
        "for real sources. "
        "Pass mark: no site passes every gate.",
        "",
        f"**{len(done)} of {len(rows)} sites ran. {len(passing)} passed every gate.**",
        "",
        "| site | region | stratum | days used | gates failed | estimate t/yr |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        est = "" if r["est_t_yr"] is None else f"{r['est_t_yr']:.0f}"
        g = r["gates_failed"]
        failed = "did not run" if g is None else g or "NONE"
        lines.append(
            f"| {r['subject_id']} {r['name']} | {r['region']} | {r['stratum']} | "
            f"{r['days_used'] if r['days_used'] is not None else ''} | "
            f"{failed} | {est} |"
        )
    lines += ["", "## Gates failed, count of sites", "", "| gate | sites |", "|---|---|"]
    lines += [f"| {g} | {n} |" for g, n in gate_counts(done).items()]
    lines += [
        "",
        "## By stratum",
        "",
        "| region | stratum | sites | passed all gates | mean gates failed |",
    ]
    lines.append("|---|---|---|---|---|")
    for region in ("europe", "us"):
        for stratum in ("far", "shadow"):
            cell = [r for r in done if r["region"] == region and r["stratum"] == stratum]
            if cell:
                mean = sum(r["n_gates_failed"] for r in cell) / len(cell)
                n_pass = sum(bool(r["passes_all_gates"]) for r in cell)
                lines.append(f"| {region} | {stratum} | {len(cell)} | {n_pass} | {mean:.1f} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise the null test")
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--in-dir", type=Path, default=extract.INTERIM_DIR)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--level", default=None, choices=["100m", "500m"], help="wind level")
    args = parser.parse_args()
    level = args.level or wind_level()
    sites = json.loads(null_sites.OUT_JSON.read_text(encoding="utf-8"))
    rows = [site_row(s, args.year, args.in_dir, level) for s in sites]
    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "null_test.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    text = report_markdown(rows, args.year, level)
    (args.out / "null_test.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
