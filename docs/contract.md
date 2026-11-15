# Data contract v1

The pipeline publishes JSON under `web/public/data/v1/` and the site reads it. The shape is
defined once, in `pipeline/orbyt/core/contracts.py` (Pydantic models, unknown keys refused).

| File | Content |
|---|---|
| `manifest.json` | Build time, data version (year and month), git commit, the modules and their method version |
| `pollution-hunter/findings.json` | One finding per subject, the register side and, where it passed every gate, the satellite side |
| `pollution-hunter/finding/<id>.json` | The reported series, and where available the plume profile, days, evidence images, the two-period comparison and the rolling windows |

## From model to site

```
contracts.py  ->  schemas/*.schema.json  ->  web/src/data/types.ts
```

```
cd pipeline
uv run python -m orbyt.core.publish --types
```

This validates every published file against the models (a finding without its detail file, a
detail file without a finding, a wrong count, a key the models do not know all fail), writes
`manifest.json`, exports the schemas, and generates the TypeScript types with `npx
json-schema-to-typescript`. Do not edit `types.ts` by hand. `test_contracts.py` fails when the
committed schemas are out of date.

## Rules for changing it

- The path says the version. A change that removes or renames a key, or changes its meaning,
  goes to `/data/v2/`. Adding an optional key stays in v1.
- Optional keys are left out of the JSON when empty. `null` means the value is known to be missing.
- `observed`, `ratio`, `verdict` and `grade` are set only where the published estimate passed
  every quality gate. A subject with a "higher" call stays register-side only until its id is in
  `higher_review.json` (PLAN.md 7.2).
