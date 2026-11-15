"""Run extract, wind and every estimate for the European subjects (M5.2).

    uv run python -m orbyt.modules.pollution_hunter.eu_run
    uv run python -m orbyt.modules.pollution_hunter.eu_run --only ph-eu-12a5336d

For each subject of ``eu_subjects.json``, in its order (reliable size first, then the rest):

1. download the usable overpass patches from ``europe.first_day`` to the latest data (extract.py),
2. fetch the 100 m wind of every cached day (era5.py), again when new days were added,
3. write ``estimate-<year>.json`` and its diagnostic for each register year (observe.py),
4. write ``rolling.json``: the estimate of every rolling 12-month window (windows.py).

Everything is resumable: cached patches are not downloaded again and a register year whose
estimate file exists is kept. A subject that fails is logged and the run goes on. The log is
``data/interim/eu_batch_log.jsonl``, one line per subject and step.
"""

from __future__ import annotations

import argparse
import json
import time
import traceback
from datetime import UTC, date, datetime
from pathlib import Path

from orbyt.modules.pollution_hunter import eu_set, extract, observe, windows
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import era5, gee

LOG = extract.INTERIM_DIR / "eu_batch_log.jsonl"


def _log(entry: dict, path: Path = LOG) -> None:
    entry["at"] = datetime.now(UTC).isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def subject_ids(path: Path = eu_set.SUBJECTS_JSON) -> list[str]:
    return [s["subject_id"] for s in json.loads(path.read_text(encoding="utf-8"))]


def _winds_current(out_dir: Path, subject_id: str) -> bool:
    """True when wind.json holds a row for every cached patch."""
    path = era5.wind_path(out_dir, subject_id)
    if not path.exists():
        return False
    n_patches = len(list((out_dir / subject_id).glob("*.npz")))
    return len(json.loads(path.read_text(encoding="utf-8"))["days"]) >= n_patches


def run_subject(
    subject_id: str, until: date, workers: int, out_dir: Path, log=print
) -> dict[str, int]:
    cfg = load_config()
    first_day = date.fromisoformat(cfg["europe"]["first_day"])
    years = cfg["europe"]["register_years"]
    subject = extract.load_subject(subject_id)
    log(f"{subject_id}: {ascii(subject.name)} at {subject.lat:.3f}, {subject.lon:.3f}")
    t0 = time.time()
    res = extract.extract_subject(
        subject, first_day, until, out_dir=out_dir, workers=workers, log=log
    )
    _log(
        {
            "subject_id": subject_id,
            "step": "extract",
            "days": res.n_days,
            "downloaded": res.n_downloaded,
            "seconds": round(time.time() - t0),
        }
    )
    if not _winds_current(out_dir, subject_id):
        era5.winds_for_subject(subject_id, out_dir, log=log)
    for y in years:
        path = out_dir / subject_id / observe.estimate_name(y)
        if path.exists():
            log(f"{subject_id}: {path.name} exists, kept")
            continue
        observe.observe_subject(subject_id, out_dir, log=log, year=y)
        doc = json.loads(path.read_text(encoding="utf-8"))
        _log(
            {
                "subject_id": subject_id,
                "step": "observe",
                "year": y,
                "nox_t_yr": (doc["observed"] or {}).get("nox_t_yr"),
                "gates_failed": doc["gates_failed"],
                "days_used": doc["days"]["used"],
            }
        )
    winds = era5.read_winds(era5.wind_path(out_dir, subject_id))
    data_end = max(date.fromisoformat(w.day) for w in winds)
    wins = windows.rolling_windows(first_day, data_end, cfg["europe"]["window_months"])
    doc = windows.estimate_windows(subject_id, wins, out_dir, log=log)
    windows.write_rolling(doc, out_dir)
    summary = windows.summarise(doc)
    _log({"subject_id": subject_id, "step": "rolling", "data_end": data_end.isoformat(), **summary})
    log(f"{subject_id}: rolling {summary}, {round(time.time() - t0)} s")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate the European subjects")
    parser.add_argument("--only", nargs="+", help="run only these subject ids")
    parser.add_argument("--until", type=date.fromisoformat, default=date.today())
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out-dir", type=Path, default=extract.INTERIM_DIR)
    args = parser.parse_args()
    ids = args.only or subject_ids()
    gee.init()
    failed = []
    for n, sid in enumerate(ids, start=1):
        print(f"--- {n}/{len(ids)} {sid}", flush=True)
        try:
            run_subject(sid, args.until, args.workers, args.out_dir)
        except Exception as exc:  # one bad subject must not stop the run
            traceback.print_exc()
            _log({"subject_id": sid, "step": "failed", "error": f"{type(exc).__name__}: {exc}"})
            failed.append(sid)
    print(f"done: {len(ids) - len(failed)} of {len(ids)} subjects; failed: {failed or 'none'}")


if __name__ == "__main__":
    main()
