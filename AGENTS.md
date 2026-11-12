# Rules for AI coding assistants in this repo

1. Read PLAN.md before any task. Work on one task ID from section 6 at a time.
2. Never add AI attribution: no Co-Authored-By trailers, no "generated with" lines,
   no AI names in commits, pull requests, README, comments or docs. Commits are authored by Badr only.
3. Never use em dashes in docs, UI copy or comments.
4. Pinned stack: Python 3.12, maplibre-gl ^5 (not 6), deck.gl ^9 via MapboxOverlay, React, Vite,
   Tailwind 4. Do not upgrade a major version without being asked.
5. Static only. No server code, no API routes, no database connections in web/.
6. Never invent data. No placeholder numbers in anything under dist/. Fixtures live in tests/ only.
7. pipeline/orbyt/modules/pollution_hunter/core_math.py changes only when the task says so,
   and tests/test_core_math.py must pass afterwards.
8. Constants live in config.yaml with their source. Units go in variable names.
9. UI text follows PLAN.md section 9.9. Verdict labels are fixed strings.
10. If you are unsure an API exists in the pinned version, say so and link the docs. Do not guess.
11. Write or update a test with every pipeline change.

## Local setup notes

- Dev machine is native Windows. Use `npm.cmd` (PowerShell blocks `npm.ps1`) or the cmd shell.
- Web uses npm with `web/package-lock.json`. Pipeline uses uv with `pipeline/uv.lock`.
- Earth Engine project ID: `orbyt-earth`.
