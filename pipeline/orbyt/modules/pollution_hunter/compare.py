"""Compare the satellite estimates with the register and write the European verdicts (M5.3).

    uv run python -m orbyt.modules.pollution_hunter.compare

For each subject of ``eu_subjects.json`` this reads ``estimate-<year>.json`` (observe.py) for
every register year and the footprint total the register holds for that year, applies the rules
of PLAN.md 4.8 (core/verdict.py, ``verdict.u_sys`` from config.yaml) and writes:

- the finding into ``findings.json``: the register footprint total as ``claimed``, and, when the
  headline estimate passed every gate, ``observed``, ``ratio``, ``verdict`` and ``grade``;
- the detail file: every period's footprint members and comparison, and the rolling windows;
- the plume images for the headline period, through evidence.py.

Held back: any subject with a "higher" call in any period. It is written to the review list
(``--review-dir``, outside the repository) and published as it was before, with the register side
only, until its id is in ``higher_review.json`` under ``approved``. PLAN.md 7.2 asks for a manual
review, the stacked image and a right of reply before any "higher" verdict goes public.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb

from orbyt.core import verdict as vd
from orbyt.modules.pollution_hunter import eu_set, evidence, extract, observe, site_flags, windows
from orbyt.modules.pollution_hunter.config import load_config
from orbyt.sources import cities as cities_src
from orbyt.sources import eea

REVIEW_JSON = Path(__file__).parent / "higher_review.json"
DEFAULT_REVIEW_DIR = extract.INTERIM_DIR / "review"
# Keys of a detail file that evidence.py writes for a headline estimate that passed every gate.
SATELLITE_KEYS = ("observed", "profile", "days", "evidence")


def is_cluster(subject: dict) -> bool:
    """A footprint kept as a cluster: it failed the sources check only (PLAN.md 1.7)."""
    return subject.get("selection") == "cluster"


def cluster_info(subject: dict) -> dict[str, Any] | None:
    """What the site says about a cluster: how many facilities, and the neighbour left out."""
    if not is_cluster(subject) and subject["n_facilities"] <= 1:
        return None
    info: dict[str, Any] = {"n_facilities": subject["n_facilities"]}
    near = subject.get("neighbours") or []
    if near:
        n = near[0]
        info["neighbour"] = {
            "name": n["name"],
            "reported_t": n["reported_t"],
            "distance_km": n["distance_km"],
        }
    return info


def approved_ids(path: Path = REVIEW_JSON) -> set[str]:
    """Subject ids whose "higher" result has been reviewed and may be published."""
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")).get("approved", []))


def _round(x: float | None, digits: int = 0) -> float | int | None:
    if x is None:
        return None
    return round(x, digits) if digits else round(x)


def read_estimate(interim_dir: Path, subject_id: str, year: int) -> dict | None:
    path = interim_dir / subject_id / observe.estimate_name(year)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def evaluate_period(
    subject: dict, year: int, interim_dir: Path, rules: vd.Rules, method: str
) -> dict[str, Any]:
    """One register year: the footprint total, the estimate, and what they say together."""
    fp = subject["years"].get(str(year))
    est = read_estimate(interim_dir, subject["subject_id"], year)
    if est is not None and est["method"] != method:
        raise SystemExit(f"{subject['subject_id']} {year} is from {est['method']}: rerun eu_run")
    obs = (est or {}).get("observed")
    gates = (est or {}).get("gates_failed", ["no_estimate"])
    call = vd.call_period(
        str(year),
        None if obs is None else obs["nox_t_yr"],
        None if obs is None else obs["lo"],
        None if obs is None else obs["hi"],
        None if fp is None else fp["footprint_t"],
        gates,
        rules,
    )
    fit = ((est or {}).get("profile") or {}).get("fit") or {}
    return {
        "year": year,
        "footprint": fp,
        "estimate": est,
        "observed": obs,
        "gates_failed": gates,
        "n_days": None if est is None else est["days"]["used"],
        "t0_h": fit.get("t0"),
        "r2": fit.get("r2"),
        "call": call,
    }


def evaluate(
    subject: dict, flags: dict, interim_dir: Path, rules: vd.Rules, cfg: dict
) -> dict[str, Any]:
    """The verdict of one subject, with every period kept for the detail file and the review."""
    years = sorted(cfg["europe"]["register_years"])
    periods = [
        evaluate_period(subject, y, interim_dir, rules, cfg["method_version"]) for y in years
    ]
    verdict, reason = vd.combine([p["call"] for p in periods], rules)
    paired = [p for p in periods if p["call"].status != "unpaired"]
    head = paired[-1] if paired else None
    grade = (
        vd.grade(
            verdict,
            head["n_days"],
            subject["n_facilities"],
            flags["flags"],
            rules,
            cluster=is_cluster(subject),
        )
        if head
        else None
    )
    head_passes = head is not None and head["observed"] is not None and not head["gates_failed"]
    return {
        "subject": subject,
        "flags": flags,
        "periods": periods,
        "headline": head,
        "verdict": verdict,
        "reason": reason,
        "grade": grade,
        "head_passes": head_passes,
        "exceeds_higher": [p["year"] for p in periods if p["call"].status == "higher"],
    }


def _ratio_json(r: vd.Ratio | None) -> dict | None:
    return (
        None
        if r is None
        else {"value": round(r.value, 2), "lo": round(r.lo, 2), "hi": round(r.hi, 2)}
    )


def period_json(p: dict[str, Any]) -> dict[str, Any]:
    """A period as published: numbers only where the estimate passed every gate."""
    fp, call = p["footprint"], p["call"]
    ok = p["observed"] is not None and not p["gates_failed"]
    obs = p["observed"]
    return {
        "year": p["year"],
        "reported_t": None if fp is None else round(fp["footprint_t"], 1),
        "members": [] if fp is None else fp["members"],
        "status": call.status,
        "reason": call.reason,
        "observed": None
        if not ok
        else {
            "value": round(obs["nox_t_yr"]),
            "lo": round(obs["lo"]),
            "hi": round(obs["hi"]),
            "n_days": p["n_days"],
            "lifetime_h": round(obs["lifetime_h"], 1),
        },
        "ratio": _ratio_json(call.ratio) if ok else None,
        "gates_failed": p["gates_failed"],
    }


def rolling_json(interim_dir: Path, subject_id: str) -> list[dict[str, Any]]:
    """The rolling windows as published: a number only where the window passed every gate."""
    path = interim_dir / subject_id / windows.rolling_name()
    if not path.exists():
        return []
    out = []
    for w in windows.read_rolling(path)["windows"]:
        ok = windows.passing(w)
        out.append(
            {
                "start": w["start"],
                "end": w["end"],
                "label": w["label"],
                "calendar_year": w["calendar_year"],
                "n_days": w["n_days"],
                "passed": ok,
                "value": _round(w["nox_t_yr"]) if ok else None,
                "lo": _round(w["lo"]) if ok else None,
                "hi": _round(w["hi"]) if ok else None,
                "gates_failed": w["gates_failed"],
            }
        )
    return out


def build_finding(
    result: dict[str, Any], existing: dict | None, target_year: int, display_names: dict, cfg: dict
) -> dict[str, Any]:
    """The finding for the headline period. The satellite side is filled by ``publish``."""
    s, head = result["subject"], result["headline"]
    year = head["year"]
    fp = head["footprint"]
    ccfg = cfg["candidates"]
    subject = (existing or {}).get("subject") or {
        "id": s["subject_id"],
        "kind": "facility",
        "name": s["name"],
        "display_name": display_names.get(s["register_id"]),
        "operator": None,
        "sector": s["sector"],
        "country": eea.COUNTRY_ISO2.get(s["country"], s["country"]),
        "city": s["city"],
        "lat": s["lat"],
        "lon": s["lon"],
        "register": "EEA",
        "register_id": s["register_id"],
    }
    info = cluster_info(s)
    subject = {**subject, "kind": "cluster" if info else "facility"}
    period = {"label": str(year), "start": f"{year}-01-01", "end": f"{year}-12-31"}
    if year != target_year:
        period["note"] = (
            f"No {target_year} value in the register for this facility. "
            f"Latest year reported: {year}."
        )
    finding = {
        "id": f"{s['subject_id']}-{year}",
        "module": "pollution-hunter",
        "subject": subject,
        "period": period,
        "claimed": {
            "value": round(fp["footprint_t"], 1),
            "unit": "t NOx/yr",
            "basis": "unknown",
            "source": eea.SOURCE,
            "n_facilities": len(fp["members"]),
        },
        "observed": None,
        "ratio": None,
        "verdict": None,
        "grade": None,
        "detection": eea.detection_label(
            fp["footprint_t"], ccfg["footprint_km"], ccfg["reliable_min_t"]
        ),
    }
    if info:
        finding["cluster"] = info
    return finding


def footprint_series(con: duckdb.DuckDBPyConnection, register_id: str, radius_km: float) -> list:
    """The footprint total of every register year in which the anchor facility reported."""
    years = [
        r[0]
        for r in con.execute(
            "select year from reported where facility_id = ? order by year", [register_id]
        ).fetchall()
    ]
    out = []
    for y in years:
        fp = eu_set.footprint_in_year(eu_set.year_rows(con, y), register_id, radius_km)
        if fp:
            out.append({"year": y, "value": fp["footprint_t"], "basis": "unknown"})
    return out


def publish_side(result: dict[str, Any], approved: set[str]) -> bool:
    """Whether the satellite side of this subject may go on the public site.

    Needs a headline estimate that passed every gate, and, when any period says "higher", the
    subject's id in ``higher_review.json``.
    """
    if not result["head_passes"]:
        return False
    return not result["exceeds_higher"] or result["subject"]["subject_id"] in approved


def apply_result(finding: dict[str, Any], result: dict[str, Any], publish: bool) -> dict[str, Any]:
    """Set ratio, verdict and grade on the finding when the satellite side is published."""
    head = result["headline"]
    if publish:
        finding["ratio"] = _ratio_json(head["call"].ratio)
        finding["verdict"] = result["verdict"]
        finding["grade"] = result["grade"]
    elif not head["gates_failed"] and result["exceeds_higher"]:
        pass  # held for review: the register side only, as before
    else:
        # Gates failed: no number, and the verdict says why there is none.
        finding["verdict"] = result["verdict"]
    return finding


def detail_json(
    result: dict[str, Any],
    base: dict | None,
    series: list,
    interim_dir: Path,
    publish: bool,
    u_sys: float,
) -> dict[str, Any]:
    """The detail file: kept keys of ``base``, the reported series and, if published, periods."""
    s = result["subject"]
    doc = dict(base or {})
    doc["id"] = f"{s['subject_id']}-{result['headline']['year']}"
    doc["reported_series"] = series
    doc["sources"] = list(dict.fromkeys([*doc.get("sources", []), eea.SOURCE]))
    if publish or not result["exceeds_higher"]:
        doc["comparison"] = {
            "u_sys": u_sys,
            "verdict_reason": result["reason"],
            "flags": result["flags"]["flags"],
            "periods": [period_json(p) for p in result["periods"]],
        }
        doc["rolling"] = rolling_json(interim_dir, s["subject_id"])
    else:
        doc.pop("comparison", None)
        doc.pop("rolling", None)
    if not (publish and result["head_passes"]):
        # The satellite side evidence.py added for an earlier estimate. It must go when the
        # headline no longer passes every gate, or the panel would draw the old estimate.
        for key in SATELLITE_KEYS:
            doc.pop(key, None)
    return doc


def merge(
    payload: dict,
    built: list[tuple[dict, dict]],
    detail_dir: Path,
) -> None:
    """Replace each subject's finding in the payload (or add it) and write its detail file."""
    for finding, detail in built:
        sid = finding["subject"]["id"]
        at = next((i for i, f in enumerate(payload["findings"]) if f["subject"]["id"] == sid), None)
        if at is None:
            payload["findings"].append(finding)
        else:
            old_id = payload["findings"][at]["id"]
            payload["findings"][at] = finding
            if old_id != finding["id"]:
                (detail_dir / f"{old_id}.json").unlink(missing_ok=True)
        text = json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + "\n"
        (detail_dir / f"{finding['id']}.json").write_text(text, encoding="utf-8")
    payload["count"] = len(payload["findings"])


def write_review(
    results: list[dict[str, Any]], approved: set[str], con: duckdb.DuckDBPyConnection, out_dir: Path
) -> Path:
    """The list of "higher" calls with the evidence PLAN.md 7.2 asks to check, outside the repo."""
    cfg = load_config()
    cities = cities_src.load_cities()
    flagged = [r for r in results if r["exceeds_higher"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = ["# Higher flags for review", ""]
    if not flagged:
        lines += ["No subject has a period that is called higher than reported.", ""]
    for r in flagged:
        s = r["subject"]
        state = "approved" if s["subject_id"] in approved else "HELD, not published"
        lines += [f"## {s['name']} ({s['country']}, {s['city']}) {s['subject_id']}", ""]
        lines += [
            f"- Status: {state}. Verdict by the rules: {r['verdict']}"
            + (f" ({r['reason']})" if r["reason"] else ""),
            f"- Location: {s['lat']}, {s['lon']}, https://www.openstreetmap.org/"
            f"?mlat={s['lat']}&mlon={s['lon']}#map=11/{s['lat']}/{s['lon']}",
            f"- Flags: {r['flags']['flags'] or 'none'}; sea {r['flags']['coast_km']} km, "
            f"elevation range {r['flags']['elevation_range_m']} m within 30 km",
            f"- Isolation numbers: own enhancement {s['own_enh_umol_m2']} umol/m2, "
            f"map noise {s['map_noise_umol_m2']}",
            "",
            "| Year | Reported footprint, t | Estimate, t (95% sampling interval) | Days | "
            "Ratio (95% with u_sys) | Call | Gates failed | Lifetime h | Plume start t0 h | r2 |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for p in r["periods"]:
            o, c = p["observed"], p["call"]
            ratio = (
                ""
                if c.ratio is None
                else f"{c.ratio.value:.2f} ({c.ratio.lo:.2f} to {c.ratio.hi:.2f})"
            )
            fp = "none" if p["footprint"] is None else f"{p['footprint']['footprint_t']:,.0f}"
            est = "" if o is None else f"{o['nox_t_yr']:,.0f} ({o['lo']:,.0f} to {o['hi']:,.0f})"
            life = "" if o is None else f"{o['lifetime_h']:.1f}"
            t0 = "" if p["t0_h"] is None else f"{p['t0_h']:.2f}"
            r2 = "" if p["r2"] is None else f"{p['r2']:.2f}"
            lines.append(
                f"| {p['year']} | {fp} | {est} | {p['n_days']} | {ratio} | {c.status} | "
                f"{', '.join(p['gates_failed']) or 'none'} | {life} | {t0} | {r2} |"
            )
        lines += [
            "",
            "Register footprint members (PLAN.md 7.2: the total must hold every facility):",
        ]
        for p in r["periods"]:
            if p["footprint"]:
                for m in p["footprint"]["members"]:
                    lines.append(f"- {p['year']}: {ascii(m['name'])} {m['reported_t']:,.0f} t")
        series = eea.reported_series(con, [s["register_id"]])[s["register_id"]]
        lines += [
            "",
            "Register series of the anchor facility (a known data error shows as a jump):",
            ", ".join(f"{x['year']}: {x['value']:,.0f}" for x in series),
            "",
            "Populated places within 30 km (towns, cities; Natural Earth), to check against the "
            "plume start:",
        ]
        near = cities.near(s["lat"], s["lon"], 30, 0)
        lines += [
            f"- {c['name']} {c['population']:,} people, {c['distance_km']:.0f} km" for c in near[:8]
        ]
        if not near:
            lines.append("- none listed")
        lines += [
            "",
            "Rolling windows that passed every gate:",
            ", ".join(
                f"{w['label']}: {w['value']:,}"
                for w in rolling_json(extract.INTERIM_DIR, s["subject_id"])
                if w["passed"]
            )
            or "none",
            "",
            "Stacked image and curve for each year (look at them, the plume must start at the "
            "site):",
        ]
        for p in r["periods"]:
            png = observe.estimate_name(p["year"], "diagnostic", ".png")
            lines.append(f"- {p['year']}: {extract.INTERIM_DIR / s['subject_id'] / png}")
        lines += [
            "",
            "Still to do by hand (PLAN.md 7.2): unlisted sources within 30 km on the map (ports, "
            "motorways, other industry), coast and mountain artefacts, right of reply to the "
            f"operator before publishing, then add the id to {REVIEW_JSON.name}.",
            "",
        ]
    path = out_dir / "higher_flags.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    cfg_u = cfg["verdict"]["u_sys"]
    (out_dir / "higher_flags.json").write_text(
        json.dumps(
            {
                "u_sys": cfg_u,
                "flagged": [
                    {
                        "subject_id": r["subject"]["subject_id"],
                        "name": r["subject"]["name"],
                        "years_higher": r["exceeds_higher"],
                        "verdict": r["verdict"],
                        "approved": r["subject"]["subject_id"] in approved,
                    }
                    for r in flagged
                ],
            },
            indent=1,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def run(
    interim_dir: Path = extract.INTERIM_DIR,
    findings_path: Path = evidence.FINDINGS,
    review_dir: Path = DEFAULT_REVIEW_DIR,
    with_evidence: bool = True,
    only: list[str] | None = None,
    log=print,
) -> list[dict[str, Any]]:
    cfg = load_config()
    rules = vd.rules_from_config(cfg)
    subjects = json.loads(eu_set.SUBJECTS_JSON.read_text(encoding="utf-8"))
    if only:
        subjects = [s for s in subjects if s["subject_id"] in only]
    flags = json.loads(site_flags.FLAGS_JSON.read_text(encoding="utf-8"))["sites"]
    approved = approved_ids()
    con = duckdb.connect(str(eea.WAREHOUSE_DIR / "orbyt.duckdb"), read_only=True)
    payload = json.loads(findings_path.read_text(encoding="utf-8"))
    target = int(payload["period"])
    names = eea.load_display_names()
    results, built, to_publish = [], [], []
    for s in subjects:
        r = evaluate(s, flags[s["subject_id"]], interim_dir, rules, cfg)
        results.append(r)
        existing = next(
            (f for f in payload["findings"] if f["subject"]["id"] == s["subject_id"]), None
        )
        publish = publish_side(r, approved)
        finding = apply_result(build_finding(r, existing, target, names, cfg), r, publish)
        series = footprint_series(con, s["register_id"], cfg["candidates"]["footprint_km"])
        detail_path = findings_path.parent / "finding" / f"{finding['id']}.json"
        base = json.loads(detail_path.read_text(encoding="utf-8")) if detail_path.exists() else None
        built.append((finding, detail_json(r, base, series, interim_dir, publish, rules.u_sys)))
        if publish:
            to_publish.append((s["subject_id"], r["headline"]["year"]))
        log(
            f"{s['subject_id']} {ascii(s['city'])[:16]:16s} headline {r['headline']['year']} "
            f"verdict {r['verdict']} grade {r['grade']}"
            + (" HELD" if r["exceeds_higher"] and not publish else "")
        )
    merge(payload, built, findings_path.parent / "finding")
    findings_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    if with_evidence:
        for sid, year in to_publish:
            evidence.publish_subject(sid, year=year, log=log)
    write_review(results, approved, con, review_dir)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the European verdicts")
    parser.add_argument("--review-dir", type=Path, default=DEFAULT_REVIEW_DIR)
    parser.add_argument("--no-evidence", action="store_true", help="skip the plume images")
    parser.add_argument("--only", nargs="+", help="only these subject ids")
    args = parser.parse_args()
    results = run(review_dir=args.review_dir, with_evidence=not args.no_evidence, only=args.only)
    held = [r for r in results if r["exceeds_higher"]]
    print(f"{len(results)} subjects, {len(held)} with a higher call (review: {args.review_dir})")


if __name__ == "__main__":
    main()
