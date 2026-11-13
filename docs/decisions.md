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

## 2026-11-13, M3.1 and M3.2

- Test facility: Belchatow power station (`ph-eu-a43eff1e`), the largest reporter with no other large source within the isolation radius. It is the first facility run end to end, so a bad fit points at the method and not at a neighbour.
- `core_math.py` is Appendix A block 1 copied unchanged, and `test_core_math.py` is block 2 with only the import path changed. Ruff rule B023 flags the plan's `plume()` closure in that test as a false positive, so it is ignored for that one file in `pyproject.toml` rather than editing the plan's code.
- Constants for the module live in `pollution_hunter/config.yaml`, each with its source, and are read through `config.py`.
- Overpass filter runs on the Earth Engine server, month by month: solar zenith 65 degrees or less, sensor zenith 56 degrees or less, and at least half of a 50 km disc valid. Where several images fall on one UTC day, the one with the smallest sensor zenith is kept.
- 2024 gave 128 usable images on 117 days. November and December have none because the sun is too low at 51 degrees north.
- Patches are 0.03 degree grids, 109 x 173 cells, 180 km each way from the source, cached as compressed NPZ under `data/interim/<subject id>/`. Re-running skips days already cached.
- Measured cost of one facility-year: 144.7 EECU-seconds, or 0.04 EECU-hours, against the 150 hours a month of the community tier. The listing is almost all of it. Earth Engine did not return a profile for every call (10 of 12 listing calls and 103 of 117 patch calls), so the figure is scaled up by the share found.
- Image start and end times are the window of about an hour of track, not the moment the satellite passed the source. M3.3 derives that moment from the solar zenith and azimuth at the source and checks it falls inside the window.

## 2026-11-13, M3.3

- Wind comes from ERA5 hourly 100 m u and v, read from the 0.25 degree cell that holds the source, at the whole UTC hour nearest the pass. All 117 days of Belchatow 2024 had a wind value. Speeds run 1.1 to 9.7 m/s with a median of 4.6.
- The pass time is worked out from the solar zenith angle and azimuth at the source (negative azimuth is west of south, so afternoon), the declination and the equation of time. 115 of 117 days land inside the image window. The other 2 use the plan's fixed 13:30 local solar time, and each day in wind.json records which one it used (pass_source).
- Over Poland the satellite sees the source close to solar noon on many days (zenith angle within a degree or two of the noon value), not at 13:30. The fixed 13:30 rule would be about 1.5 to 2 hours late on those days, which is one to two ERA5 hours of wind change.
- The 100 m level is the only level read so far. The plan's test of the 500 m level (pressure level collection) is left for M3.5.
- The 2 m/s minimum wind is in config.yaml as wind.min_speed_ms and is applied in M3.4, so wind.json keeps every day.

## 2026-11-13, M3.4

- observe.py runs the unchanged core_math on the 110 days with wind of at least 2 m/s (7 of 117 were calm), with the Appendix A grids (crosswind -80 to 80 km in 2 km steps, travel time -2 to 6 h in 0.1 h steps), NOx to NO2 1.38 and air mass correction 1.61. It writes estimate.json and diagnostic.png next to the patches.
- First result for Belchatow 2024: 13,638 t NOx/yr, bootstrap interval 10,337 to 38,299, against 18,800 reported (ratio 0.73). Two gates fail: lifetime_out_of_range (the fitted lifetime sits on its 12 h upper bound) and low_signal_to_noise. It is not published as a number. M3.5 is where the cause is looked at.
- What the figure shows: a clear plume that starts at the source, a sharp rise in the stacked flux over the first hour, then a flat plateau out to 6 h instead of a decay. A plateau like that means the background is not fully removed downwind or other sources add NO2 along the track, so the long tail is not the plant. The EMG fit r2 is 0.93, so a good r2 alone does not mean a good estimate.
- Not changed: core_math.py, the 100 m wind level, the upwind background box.
