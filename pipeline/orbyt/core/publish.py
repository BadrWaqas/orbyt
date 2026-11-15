"""Export the JSON Schemas, validate the published data and write the manifest (M5.5).

    uv run python -m orbyt.core.publish            # validate, then write manifest.json
    uv run python -m orbyt.core.publish --schemas  # also write schemas/*.json
    uv run python -m orbyt.core.publish --types    # schemas, then web/src/data/types.ts (npx)

Validation covers ``findings.json`` and every ``finding/<id>.json`` of each module, and checks
that each finding has its detail file and that no detail file is orphaned. TypeScript types
for the web app are generated from ``schemas/contract.schema.json``, see docs/contract.md.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from orbyt.core import contracts as c

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = REPO_ROOT / "web" / "public" / "data" / "v1"
SCHEMAS_DIR = REPO_ROOT / "schemas"
SCHEMA_ID = "https://orbytearth.com/schemas/v1/{name}.schema.json"
DATA_BASE = "/data/v1"

MODELS: dict[str, type[c.Model]] = {
    "manifest": c.Manifest,
    "findings": c.FindingsPayload,
    "finding_detail": c.FindingDetail,
}


def tidy(node: Any, is_property: bool = False) -> Any:
    """Make the schema friendlier to code generators.

    Pydantic titles every property, which makes the TypeScript generator invent a type alias per
    field, so property titles are dropped (definitions keep theirs). Tuples are written with
    ``prefixItems``, which generators do not read, so they become an ``items`` list.
    """
    if isinstance(node, list):
        return [tidy(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {}
    for key, value in node.items():
        if key == "title" and is_property:
            continue
        if key == "properties":
            out[key] = {k: tidy(v, is_property=True) for k, v in value.items()}
        elif key == "prefixItems":
            out["items"] = tidy(value)
        else:
            out[key] = tidy(value)
    return out


def schema_of(model: type[c.Model], name: str) -> dict[str, Any]:
    s = tidy(model.model_json_schema(mode="serialization", by_alias=True))
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID.format(name=name),
        **s,
    }


def export_schemas(out_dir: Path = SCHEMAS_DIR) -> list[Path]:
    """One schema per public document, plus ``contract`` with every definition for codegen."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, model in {**MODELS, "contract": c.Contract}.items():
        path = out_dir / f"{name}.schema.json"
        text = json.dumps(schema_of(model, name), indent=2, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_module(module_dir: Path) -> dict[str, int]:
    """Validate one module's findings and detail files. Raises on the first problem."""
    payload = c.FindingsPayload.model_validate(_read(module_dir / "findings.json"))
    if payload.count != len(payload.findings):
        raise ValueError(
            f"{module_dir.name}: count {payload.count} but {len(payload.findings)} findings"
        )
    ids = [f.id for f in payload.findings]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{module_dir.name}: duplicate finding ids")
    subjects = [f.subject.id for f in payload.findings]
    if len(set(subjects)) != len(subjects):
        raise ValueError(f"{module_dir.name}: a subject has more than one finding")
    detail_dir = module_dir / "finding"
    on_disk = {p.stem for p in detail_dir.glob("*.json")}
    missing, orphan = set(ids) - on_disk, on_disk - set(ids)
    if missing or orphan:
        raise ValueError(
            f"{module_dir.name}: missing detail {sorted(missing)[:5]}, orphan {sorted(orphan)[:5]}"
        )
    for fid in ids:
        detail = c.FindingDetail.model_validate(_read(detail_dir / f"{fid}.json"))
        if detail.id != fid:
            raise ValueError(f"{fid}: detail file says id {detail.id}")
    return {"findings": len(ids), "details": len(ids)}


TYPES_TS = REPO_ROOT / "web" / "src" / "data" / "types.ts"
BANNER = (
    "/* The data contract of /data/v1 (PLAN.md 2.5 and Appendix B).\n"
    " * GENERATED from schemas/contract.schema.json, which comes from\n"
    " * pipeline/orbyt/core/contracts.py. Do not edit by hand. Regenerate with\n"
    " *   uv run python -m orbyt.core.publish --schemas --types\n"
    " */"
)


def generate_types(schema: Path | None = None, out: Path = TYPES_TS) -> Path:
    """Write the web app's TypeScript types from the combined schema, with npx."""
    schema = schema or SCHEMAS_DIR / "contract.schema.json"
    npx = "npx.cmd" if os.name == "nt" else "npx"
    subprocess.run(
        [
            npx,
            "--yes",
            "json-schema-to-typescript@15",
            "-i",
            str(schema),
            "-o",
            str(out),
            "--no-additionalProperties",
            "--unreachableDefinitions",
            "--bannerComment",
            BANNER,
        ],
        cwd=REPO_ROOT,
        check=True,
    )
    return out


def git_commit(root: Path = REPO_ROOT) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build_manifest(method_version: str, data_version: str, commit: str) -> c.Manifest:
    return c.Manifest(
        built_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        data_version=data_version,
        commit=commit,
        modules=[
            c.ModuleEntry(
                id="pollution-hunter",
                title="Pollution Hunter",
                hue="amber",
                status="live",
                method_version=method_version,
                base=f"{DATA_BASE}/pollution-hunter",
            )
        ],
    )


def publish(data_root: Path = DATA_ROOT, schemas: bool = False, log=print) -> c.Manifest:
    """Validate every module under ``data_root`` and write ``manifest.json``."""
    from orbyt.modules.pollution_hunter.config import load_config

    cfg = load_config()
    counts = {}
    for module_dir in sorted(p for p in data_root.iterdir() if (p / "findings.json").exists()):
        counts[module_dir.name] = validate_module(module_dir)
        log(f"{module_dir.name}: {counts[module_dir.name]} valid")
    manifest = build_manifest(
        cfg["method_version"], datetime.now(UTC).strftime("%Y-%m"), git_commit()
    )
    (data_root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if schemas:
        for p in export_schemas():
            log(f"schema {p.relative_to(REPO_ROOT)}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the published data, write the manifest")
    parser.add_argument("--schemas", action="store_true", help="also write schemas/*.json")
    parser.add_argument("--types", action="store_true", help="also generate web/src/data/types.ts")
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = parser.parse_args()
    publish(args.data_root, schemas=args.schemas or args.types)
    if args.types:
        print(f"types {generate_types().relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
