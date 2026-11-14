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
from orbyt.sources import era5, gee

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


def run_subject(subject_id: str, years: list[int], workers: int, out_dir: Path, log=print) -> None:
    """Extract, wind and estimates for the years that have no estimate file yet."""
    todo = [y for y in years if not (out_dir / subject_id / observe.estimate_name(y)).exists()]
    if not todo:
        log(f"{subject_id}: all years done")
        return
    subject = extract.load_subject(subject_id)
    log(
        f"{subject_id}: {ascii(subject.name)} at {subject.lat:.3f}, {subject.lon:.3f}, years {todo}"
    )
    t0 = time.time()
    for y in todo:
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
    era5.winds_for_subject(subject_id, out_dir, log=log)
    for y in todo:
        path = observe.observe_subject(subject_id, out_dir, log=log, year=y)
        doc = json.loads(path.read_text(encoding="utf-8"))
        _log(
            {
                "subject_id": subject_id,
                "year": y,
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
            run_subject(sid, args.years, args.workers, args.out_dir)
        except Exception as exc:  # one bad subject must not stop the batch
            traceback.print_exc()
            _log({"subject_id": sid, "step": "failed", "error": f"{type(exc).__name__}: {exc}"})
            failed.append(sid)
    print(f"done: {len(ids) - len(failed)} of {len(ids)} subjects; failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
