# Orbyt Earth

Fact-checking the world from space. Each module puts what was officially reported next to what a satellite measured, and shows the gap on a 3D globe. Module 1 is Pollution Hunter: NOx emissions from large facilities, measured with Sentinel-5P.

Status: milestone M0, a dark spinning globe. The full plan is in [PLAN.md](PLAN.md).

## Run the web app

```
cd web
npm install
npm run dev
```

On Windows PowerShell use `npm.cmd` in place of `npm`.

## Run the pipeline checks

```
cd pipeline
uv sync
uv run ruff check .
uv run pytest
```

## Layout

- `web/` Vite, React, TypeScript, Tailwind, MapLibre GL JS v5
- `pipeline/` Python package `orbyt`: data sources, modules, tests
- `schemas/` JSON Schema for the published data contract
- `docs/` decisions and diagrams

## Licence

Code is MIT. Data sources keep their own licences, listed in [DATA_LICENSES.md](DATA_LICENSES.md).
