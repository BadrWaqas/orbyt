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


## 2026-11-12, M1.1 and M1.2

- Earth Engine is authenticated on the dev machine with `earthengine authenticate` (credentials live in the user profile, never in the repo) and the default project is set with `earthengine set_project orbyt-earth`.
- The 2024 NO2 collection holds 5,164 images with processor versions 2.6.0, 2.7.1 and 2.8.0, all after the July 2022 change noted in PLAN.md.
- The global 0.1 degree annual mean is downloaded in 300 x 300 cell windows, 8 at a time. A 600 x 600 window of a full year mean did not return within several minutes.
- Earth Engine serves the 0.1 degree grid from its image pyramid, so each cell is the mean of the finer cells inside it.

## 2026-11-12, M1.3 and M1.5

- Plume ramp: the 0 to 1 position is linear in the square root of the value between 20 and 250 micromol/m2, clipped at both ends. At 20 or below the layer is fully transparent, so most of the ocean and clean land shows no colour. All 341 tiles are written, including empty ones, so the map never asks for a missing tile.
- Tiles are 256 px Web Mercator PNGs for zoom 0 to 4 in `web/public/tiles/no2-2024/` (1.4 MB), committed because Cloudflare Pages builds from git. The tile source grid is the 0.1 degree annual mean, resampled bilinearly, so zoom 4 is slightly soft by design.
- EEA v16: the CSV bundle (148 MB) comes from the EEA public download share. Only `F1_4_Air_Releases_Facilities.csv` is used. Releases are in kg and are converted to tonnes. NOx is the row "Nitrogen oxides (NOX)", expressed as NO2.
- The CSV bundle has no measured, calculated or estimated column, so `claimed.basis` is `"unknown"` in `findings.json`. The first panel must show "unknown" rather than guess. The Access database in the same release (2 GB) may hold the method code. Not read yet, skipped on purpose for now.
- 2024 coverage gaps: no NOx rows for 2024 from Cyprus (last 2023), Czechia, Lithuania, Malta, Slovakia, Switzerland (last 2022), Norway (2017), the United Kingdom (2019) and Iceland (2007). The loader writes this to the `coverage` table.
- Countries without 2024 data keep their latest year. Each such finding has its real year in `period.label`, `start`, `end` and the id suffix, plus `period.note` ("Latest year reported by Czechia. No 2024 data."), and the file lists them in `latest_year_countries`. The UI must show that year wherever it shows the value. Old years (Norway 2017, the UK 2019) are not comparable with 2024 satellite data, so M2 must not pair a finding whose year is not 2024 unless the satellite year is matched to it.
- Fallback years before 2022 are dropped, so the United Kingdom (2019), Norway (2017) and Iceland (2007) are not in `findings.json`. The list is refilled to 300 with the next largest reporters.
- `findings.json` holds the 300 largest reporters (2024, or the country's latest year from 2022 on) that have coordinates, reported side only, at `web/public/data/v1/pollution-hunter/findings.json`. Facilities with withheld coordinates (confidential rows) are skipped. Ids come from a hash of the register id so they do not change when the ranking does.
