"""Run extract, wind and observe for a list of subjects, one after the other.

    uv run python -m orbyt.modules.pollution_hunter.batch --set null --years 2024
    uv run python -m orbyt.modules.pollution_hunter.batch --set us --tier 1 2 --years 2023 2024

For each subject and year this is what the three single commands do by hand: download the
overpass patches (extract.py), fetch the 100 m wind for every cached day (era5.py) and write
``estimate-<year>.json`` (observe.py). A year whose estimate file exists is skipped, so a rerun
carries on where an interrupted one stopped. A subject that fails is logged and the batch goes on.
The log is ``data/interim/batch_log.jsonl``, one line per subject and year.
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

from orbyt.modules.pollution_hunter import extract, observe
from orbyt.modules.pollution_hunter.config import wind_level
from orbyt.sources import era5, era5_levels, gee

SETS = {
    "us": extract.SUBJECT_FILES["ph-us-"],
    "null": extract.SUBJECT_FILES["ph-null-"],
}
LOG = extract.INTERIM_DIR / "batch_log.jsonl"


def subject_ids(which: str, tiers: list[int] | None = None) -> list[str]:
    """Ids of the chosen set, in file order. ``tiers`` applies to the US plants only."""
    rows = json.loads(SETS[which].read_text(encoding="utf-8"))
    if which == "us" and tiers:
        rows = [r for r in rows if r["tier"] in tiers]
    return [r["subject_id"] for r in rows]


def _log(entry: dict, path: Path = LOG) -> None:
    entry["at"] = datetime.now(UTC).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _wind_covers(path: Path, years: list[int]) -> bool:
    if not path.exists():
        return False
    days = json.loads(path.read_text(encoding="utf-8"))["days"]
    have = {int(d["day"][:4]) for d in days}
    return all(y in have for y in years)


def run_subject(
    subject_id: str,
    years: list[int],
    workers: int,
    out_dir: Path,
    levels: list[str] | None = None,
    log=print,
    redo: bool = False,
) -> None:
    """Extract, wind and estimates for the years and wind levels that have no estimate yet.

    ``redo`` estimates again even where the file exists (after a method change).
    """
    levels = levels or [wind_level()]
    todo = {
        lv: [
            y
            for y in years
            if redo or not (out_dir / subject_id / observe.estimate_name(y, level=lv)).exists()
        ]
        for lv in levels
    }
    if not any(todo.values()):
        log(f"{subject_id}: all years and levels done")
        return
    todo_years = sorted({y for ys in todo.values() for y in ys})
    subject = extract.load_subject(subject_id)
    log(f"{subject_id}: {ascii(subject.name)} at {subject.lat:.3f}, {subject.lon:.3f}, {todo}")
    t0 = time.time()
    for y in todo_years:
        res = extract.extract_subject(
            subject, date(y, 1, 1), date(y + 1, 1, 1), out_dir=out_dir, workers=workers, log=log
        )
        _log(
            {
                "subject_id": subject_id,
                "year": y,
                "step": "extract",
                "days": res.n_days,
                "downloaded": res.n_downloaded,
                "seconds": round(time.time() - t0),
            }
        )
    if not _wind_covers(era5.wind_path(out_dir, subject_id), todo_years):
        era5.winds_for_subject(subject_id, out_dir, log=log)
    for lv in levels:
        if not todo[lv]:
            continue
        if lv == "500m" and not _wind_covers(era5.wind_path(out_dir, subject_id, lv), todo[lv]):
            era5_levels.winds_500m(subject_id, out_dir, log=log)
        for y in todo[lv]:
            path = observe.observe_subject(subject_id, out_dir, log=log, year=y, level=lv)
            doc = json.loads(path.read_text(encoding="utf-8"))
            _log(
                {
                    "subject_id": subject_id,
                    "year": y,
                    "level": lv,
                    "step": "observe",
                    "nox_t_yr": (doc["observed"] or {}).get("nox_t_yr"),
                    "gates_failed": doc["gates_failed"],
                    "days_used": doc["days"]["used"],
                    "seconds": round(time.time() - t0),
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate a set of subjects")
    parser.add_argument("--set", choices=sorted(SETS), required=True)
    parser.add_argument("--tier", type=int, nargs="+", help="US plants: tiers to run (1, 2)")
    parser.add_argument("--years", type=int, nargs="+", required=True)
    parser.add_argument("--levels", nargs="+", default=None, choices=["100m", "500m"])
    parser.add_argument("--redo", action="store_true", help="estimate again where a file exists")
    parser.add_argument("--only", nargs="+", help="run only these subject ids")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out-dir", type=Path, default=extract.INTERIM_DIR)
    args = parser.parse_args()

    ids = args.only or subject_ids(args.set, args.tier)
    gee.init()
    failed = []
    for n, sid in enumerate(ids, start=1):
        print(f"--- {n}/{len(ids)} {sid}", flush=True)
        try:
            run_subject(sid, args.years, args.workers, args.out_dir, args.levels, redo=args.redo)
        except Exception as exc:  # one bad subject must not stop the batch
            traceback.print_exc()
            _log({"subject_id": sid, "step": "failed", "error": f"{type(exc).__name__}: {exc}"})
            failed.append(sid)
    print(f"done: {len(ids) - len(failed)} of {len(ids)} subjects; failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
