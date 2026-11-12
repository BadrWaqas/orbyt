# Decision log

Newest first. One line per decision, with the reason.

## 2026-11-12, milestone M0

- Repo is `BadrWaqas/orbyt`, not `orbyt-earth` as written in PLAN.md section 5.
- Development is on native Windows. WSL2 (PLAN.md M0.2) is skipped.
- Web uses npm, not pnpm. One less global tool, and Cloudflare Pages and CI both support it directly.
- Pipeline uses uv with Python pinned to 3.12 through `pipeline/.python-version`, so local runs match CI.
- No Makefile yet. `make` is not available on the Windows dev machine. Commands are in README.md.
- The globe page shows the two hero lines statically. The poster image and the timed intro belong to M7.
- Earth Engine project ID is `orbyt-earth`.
