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

## 2026-11-13, M3.5

Question: why the stacked flux for Belchatow stayed flat after the first hour, with the lifetime pinned at its 12 h bound.

Answer: leftover background, not the plant. After the single upwind median, cells 60 to 80 km to the side of the plume still held 23 to 36 micromol/m/s downwind, against 5 upwind. At 4 h that pedestal times the 80 km wide fan is about 2.9 of the 3.7 mol/s in the curve. The surroundings explain it: the Silesian conurbation 100 km south, Lodz 55 km north, and a region that is dirtier to the west and south than to the east, with wind from the east or south on 87 of the 110 days. The one clean direction, wind from the west (18 days), already gave a decaying curve with the M3.4 method (lifetime 3.8 h).

One change at a time, each from the M3.4 result. Nothing was chosen by its distance to the reported 18,800 t.

| Change | Estimate, t NOx/yr | 95% interval | Lifetime, h | Gates failed |
|---|---|---|---|---|
| M3.4 as committed | 13,638 | 10,337 to 38,299 | 12.0 (bound) | lifetime, signal to noise |
| Wind speed x1.2 (sensitivity) | 19,867 | 12,254 to 46,029 | 12.0 (bound) | lifetime, signal to noise |
| Wind turned 10 degrees clockwise (sensitivity) | 21,994 | 11,468 to 40,870 | 12.0 (bound) | lifetime, signal to noise |
| Wind turned 10 degrees anticlockwise (sensitivity) | 11,828 | 9,539 to 37,222 | 12.0 (bound) | lifetime, signal to noise |
| Upwind box 20 to 120 km | 19,050 | 10,593 to 39,183 | 12.0 (bound) | lifetime, signal to noise |
| Background from the flanks (60 to 80 km) at each travel time | 18,371 | 11,283 to 104,595 | 2.2 | signal to noise |
| Background from flanks at 80 to 120 km | 12,501 | 8,687 to 50,275 | 3.0 | signal to noise |
| Fan fixed at 20 km half-width | 11,730 | 9,984 to 14,576 | 5.6 | none |
| Fan 20 km + 0.15 per km | 10,929 | 9,404 to 13,786 | 12.0 (bound) | lifetime |
| Fan fixed at 40 km half-width | 15,143 | 12,376 to 21,085 | 9.5 | lifetime |
| Fit to 3 h | 11,857 | 9,921 to 14,870 | 12.0 (bound) | lifetime |
| Fit to 4 h | 12,466 | 10,297 to 17,577 | 12.0 (bound) | lifetime |
| Fit to 8 h | 26,104 | 9,904 to 31,716 | 12.0 (bound) | fit, plume start, lifetime |
| Fit to 10 h | 24,551 | 9,655 to 33,750 | 12.0 (bound) | fit, plume start, lifetime |
| Background plane (adopted, see below) | 15,822 | 10,013 to 97,293 | 2.7 | signal to noise |

What each test says:

- Wind level. The 500 m wind could not be tested. The Earth Engine collection `ECMWF/ERA5/HOURLY_PRESSURE_LEVELS` holds 4,288 images, a few days in 1943 and June 2026 onward, and none for 2024. Real data needs the Copernicus CDS API. The rows above scale or turn the 100 m wind instead. Neither removes the plateau, so the wind level is not its cause. It still matters for the size of the number: 20% more speed gives 26 to 46% more emission. The plume axis drifts to the right of the 100 m wind with travel time, and the centreline is strongest with the wind turned about 10 degrees clockwise. A higher transport level would do that, and the stacks are 300 m tall, so the 500 m test is worth doing in M4.4.
- Window. A shorter window does not help because the pedestal is there from the first half hour. A longer one makes it worse.
- Fan. The narrower the fan, the less pedestal it collects. That is a symptom of the background, not a reason to pick a fan. Fan width stays as in the plan until the US validation (4.9, V4).
- Background. Any rule that looks at both sides of the plume gives a curve that decays, with a lifetime of 2 to 3 h.
- Neighbours. See the last two points below.

Change made: the daily background in `core_math.py` is now a plane fitted to the upwind box and to both flanks of the scene (crosswind 60 km or more), with cells far from the plane clipped. `background_plane()` is new and `daily_flux_density()` uses it. This is the one departure from PLAN.md Appendix A, and section 4.3 step 4 and Appendix A in PLAN.md still describe the old rule.

- Why it is justified without looking at the register: one upwind value assumes the background is the same on both sides of the source. With a regional gradient and a prevailing wind it is not, the difference stays in every downwind cell, and the widening fan multiplies it.
- Synthetic proof, same scenes as the Appendix A tests plus a gradient of 12 micromol/m2 per 200 km and wind towards one side on 60% of days: the upwind median gave 2.95 and 7.78 times the truth for a 4,000 t source (lifetime at a bound) and 0.90 and 1.17 for a 20,000 t source, the second pair passing every gate. The plane gives 1.08 and 1.03, the same whichever way the gradient runs.
- On the original Appendix A scenes the plane recovers 20,000 t within 3% and 4,000 t within 5%, and still rejects the empty site and pure noise. All five Appendix A tests pass unchanged. `tests/test_background.py` adds the gradient scenes.
- A flank background per travel time was also tried. It is noisier (4,000 t recovered between 0.86 and 1.27 across seeds) and on Belchatow moves by 40% with the choice of flank, so the plane was kept.
- `flank_km: 60` is in `config.yaml`. 50 and 70 km give 16,394 and 14,385 t. `method_version` is now `ph-emg-1.1`.

Result with the plane: 15,822 t NOx/yr, interval 10,013 to 97,293, lifetime 2.7 h, r2 0.95, plume start 0.19 h. It fails `low_signal_to_noise` only and stays inconclusive.

- The good-looking all-days curve hides a disagreement. The diagnostic figure now draws the curve per wind quarter. Wind from the east (53 days) and west (18 days) agree for the first two hours, peaking near 2.5 mol/s. Wind from the south (34 days) carries the plume towards Lodz and stays above 4 mol/s to 6 h. Wind from the east goes negative after 4 h, where the Silesian outflow sits in one flank and tilts the plane. The two errors partly cancel in the all-days curve.
- What is robust: the near-source size. Every variant that keeps the first hours gives 11,000 to 16,000 t. What is not: the lifetime and so the upper end of the interval.
- Not changed: fan, window, wind level, gates, conversion constants. Those are set by the US validation.
- Isolation rule (PLAN.md 4.5) passes Belchatow and should not. It looks for register sources 20 to 60 km away and cities above 200,000 within 30 km. Lodz (about 650,000 people, 55 km) and Silesia (100 km) are inside the 6 h reach of the plume. The rule needs a check on large cities or NO2 hotspots out to about 100 km, to be decided with the candidate list in M2.

## Isolation check for cities and NO2 hotspots, candidate ranking

Why: the M3.5 result showed that the PLAN.md 4.5 rule passes Belchatow when it should not. The rule now has four parts, all set in `config.yaml` under `candidates`:

- Footprint: facilities within 20 km of each other are one subject, and the register total of the group is what counts (2,000 t or more).
- Sources: another register source above 25% of the footprint total, 20 to 60 km away, fails.
- Cities (Natural Earth 1:10m populated places, `pop_max`, public domain): 200,000 within 30 km fails, 500,000 within 100 km fails. The 500,000 is provisional and is to be set by the null test (V3), not by this list.
- Hotspots: on the 0.1 degree annual mean NO2 map for 2024, the background is the median of a 130 to 200 km ring, the facility's own enhancement is the highest cell within 12 km, and any other local maximum 20 to 100 km away above 25% of the own enhancement fails. A peak must also stand 3 robust sigmas (1.4826 x MAD of the ring) above the background, otherwise it is map noise.

Result for 2024: 839 footprints, 97 of 2,000 t or more, 8 pass all four. Without the 3 sigma floor 0 passed and 95 of 97 failed the hotspot test, which was a useless rule, so the floor is a fix to a rule that had no noise term. No threshold was moved to rescue Belchatow, which still fails (Lodz at 57 km, and a hotspot).

Passing: Atherinolakkos (Crete) 7,600 t, Maritsa East 2 (Bulgaria) 5,630 t, Los Guinchos (Tenerife) 4,020, Aalborg Portland 2,665, Dan F platform 2,643, Tornio 2,353, Thira 2,250, Eemshaven 2,020. Most are islands or weak-signal sites. Own enhancement is 4 to 12 micromol/m2 against a map noise of 1 to 5, and only Atherinolakkos and Los Guinchos are visible on the 0.1 degree map (`own_detectable`).

Checked with the real pipeline (extract, ERA5 100 m wind, observe), nothing tuned:

- Atherinolakkos, `ph-eu-12a5336d`: 255 of 272 days used, 9,124 t NOx/yr, interval 7,832 to 11,269, lifetime 1.9 h, no gate failed. Ratio to reported 1.20. The interval does not contain the reported 7,600 t, which is a fact to carry into the showcase, not something to fix.
- Maritsa East 2, `ph-eu-27eb1b72`: 138 of 171 days used, 39,871 t, interval 34,825 to 46,305, lifetime 1.0 h, fails `source_offset`. Ratio 12 against the single anchor facility (3,304 t). The lignite complex has other emitters inside the footprint and the anchor is only one of four, so the number is not a clean test of one source. Not used for the showcase.

Showcase facility: Atherinolakkos. Caveats: one oil-fired plant on an island with a clean upwind sea, which is an easy scene and a weaker test than a continental coal plant. The 0.1 degree hotspot test sees only the annual mean and not the daily scene. `tests/test_candidates.py` covers geometry, city lookup, footprints and the hotspot test on synthetic windows.

## M3.6 Single-day plume test and flipbook

`detect.py` implements PLAN.md 4.4 and writes `detect.json`, `flipbook.png` and `flipbook.json` next to `estimate.json`. Constants are in `config.yaml` under `detect`, none tuned.

- Each day is rotated onto a wind-aligned km grid (-60 to 100 km downwind), the same background plane as the estimate is subtracted, then the downwind box (0 to the smaller of 2 h of travel and 60 km, inside the fan) is compared with the mirrored upwind box. `z = (down - up) / noise`, noise is 1.4826 x MAD of the flank cells divided by the square root of the independent pixels (box area over 19 km2). Detected at z of 3 or more, and only when both boxes are at least 60% valid.
- Flipbook: a day is a frame when 80% of the shown image (-20 to 100 km downwind) is valid. Frames are drawn on the plume ramp from 0 to 100 micromol/m2 with date, wind speed and direction, z, a compass arrow for where the wind blows to, and an outline when detected. The manifest holds the grid position of each frame for the player (M3.7).

Atherinolakkos (`ph-eu-12a5336d`, 2024): plume detected on 182 of 209 testable days (255 days used), 213 frames, sheet 1830 x 6358 px, 1.3 MB.

Reading that number honestly:

- 87% is high. The same test run at three points 55 to 90 km from the plant (sea, mostly) flags 15 to 26% of days (56 of 220, 35 of 233, 53 of 187). Some of those are days when the real plume drifts into the box, but not all, so the false alarm rate on real scenes is probably above what z of 3 implies.
- The likely reason is the independence assumption. The synthetic tests use noise smoothed to one real pixel and are clean. With noise correlated over a larger area (sigma of 3 grid cells, about 800 km2 per independent value) 5 of 20 empty scenes were flagged. Real scenes also carry regional structure the plane does not remove.
- Not changed: the 19 km2 and z of 3 are from the plan. Set them from the null sites in M4 (V3), not from this plant. Until then say "plume visible on N of M days" with this caveat, and do not use the count as evidence for the estimate. The estimate does not use detect.py.
- Shuffling the wind between days is not a null for this site, because the wind is mostly from one quarter and shuffled days often match the real one (120 of 211 detected).

## M3.7 Panel evidence: plume image, curve with fit, flipbook player

`evidence.py` publishes what the panel draws for a subject whose estimate passes every gate: the estimate with its interval into `findings.json`, and into `finding/<id>.json` the stacked curve with its fit, the day list and the geometry of two images under `web/public/img/ph/<subject>/`. A subject that fails a gate is refused, so Belchatow and Maritsa East 2 stay without a number. Run it after `observe`, and again after an EEA export, which rewrites the reported side of both files.

- Estimate in the panel: 9,124 t with the bootstrap interval 7,832 to 11,269, labelled "95% interval, sampling noise only", plus a line saying the method has not been checked against stack monitors yet. No ratio, verdict, gap bar or grade: those need the verdict rules (M5) and the validated uncertainty (M4).
- Plume image: the mean over days of each day's column above its background plane, on the travel-time grid, drawn true to scale at the mean wind (one hour is as wide as the mean wind travels in it). Colours are the 9.2 ramp with its opacity over the night ocean colour, linear from 0. Its full scale is the smallest of 5, 10, 20, 50, 100, 200 micromol/m2 that holds the 99th percentile of the cells (20 for Atherinolakkos), not the 0 to 100 of the facility view, because a mean of 255 days is far weaker than one day. The key next to the image prints the range. The dashed lines are the fan the estimate integrates.
- Curve: the stacked flux as dots and the fit as a line, a rule at the source, and the two things the fit yields written into the plot. The curve is sampled every 0.1 h, which would overlap 8 px dots at panel width, so three samples are averaged into one dot. The fit line and the table keep to the same data.
- Flipbook: the web sheet is not the M3.6 sheet. Frames are maps with north up (160 km square, source at the centre), so the plume swings with the wind as PLAN.md 9.11 describes, and the labels are drawn by the page in the site's type, not baked into the image. The background plane is the one fitted in wind-aligned coordinates, evaluated on the map grid. 204 of the 255 days are clear enough (80% of the square valid). The M3.6 sheet stays as a diagnostic.
- The detected or not mark of PLAN.md 9.6 is left out, along with the count of detected days. The first frame of the year (3 January) has z of 10.3 and nothing to see in it, which is the false alarm problem from M3.6 in one picture. The per-day test results are not in the published JSON either. Bring both back once the null sites of M4 set the threshold.
- The flipbook starts playing when its tab is opened, unless the visitor prefers reduced motion. Opening the tab is the visitor's action, so this keeps to 9.1 principle 3.

## Panel and map fixes after M3.7

- Short titles. `sources/eea_display_names.yaml` holds hand-written short names for 26 facilities, keyed by register id, each a plain English rendering of the plant named in the register entry itself. `findings.json` carries them as `subject.display_name`. The panel shows the short name as the title and the register name in full under it, so PLAN.md 7.2 rule 5 still holds. A facility whose entry names only the operator (RWE Power AG in Grevenbroich, ENEA Wytwarzanie) has no short name and keeps the register name: the plant is not named in the data, so it is not guessed.
- Markers (PLAN.md 9.6). The ring is the record and keeps the ledger tone until verdicts exist. The glass fill is thinner (0.42), so the glow and neighbouring rings show through in dense areas. Markers are drawn below the place names. A facility with a satellite estimate carries an amber core and a soft amber light. The selected marker is a lit lens with a soft halo, and the others step back while a panel is open.
- NO2 glow without deck.gl: a second raster layer reads the same tiles only down to zoom 2, which stretches into the blurred copy at 40% opacity that 9.6 asks for, and the sharp layer gets a saturation of 0.25. The tiles, ramp and scale are unchanged. A contrast boost was tried and dropped, because it pushed the low end from amber to red. This softens the look but the regional wash at facility zoom is still brown: it is the ramp's low end over a real regional column. The fix that follows the plan is the facility view of 9.2, tiles of enhancement above background from 0 to 100, cross-faded in by zoom. Not built here.
- Showcase. `evidence.showcase_subject_id` in `config.yaml` is written to `findings.json` as `showcase` once that subject has an estimate. The hero has one quiet button, "Explore the globe", that flies there (PLAN.md 9.7). The second button of 9.7 waits for the method page.
- Register ID cut off: the panel was taller than the window and its last lines were clipped at the edge with no sign that it scrolls. The glass frame now stays fixed, the content scrolls inside it, and the lower edge fades while there is more below.
- An EEA export rewrites the reported side of `findings.json`, so `evidence` has to be run again after it.

## 2026-11-14, EEA export and M4.1

- An EEA export no longer wipes satellite estimates. `export_findings` reads the existing `findings.json` first and carries `observed`, `ratio`, `verdict`, `grade` and `showcase` over by finding id. The detail files keep every key the satellite side added and only `reported_series`, `id` and `sources` are refreshed. The id holds the year, so an estimate never stays next to a reported value for a different year. Because of this, `evidence` no longer has to be run again after an export (this reverses the last line of "Panel and map fixes after M3.7").
- CAMPD source: the CAMPD API and bulk files need an api.data.gov key, which this project does not have. `sources/campd.py` reads the same EPA hourly file from the PUDL public bucket (release pinned to v2026.11.0) with DuckDB, which fetches only the columns and years asked for. 2023 and 2024 for every US unit with an EIA plant id is 69.2 M unit hours, 1,363 plants, a 172 MB Parquet in `data/raw/campd/` (about a minute to fetch).
- Units: `nox_mass_lbs` is pounds of NOx expressed as NO2, the same convention as the EEA register and the satellite estimate, converted at 0.45359237 kg per lb. Plant totals for 2023 and 2024 are 0.60 Mt each, which is the size of the US power sector figure.
- Gaps: a missing NOx value almost always means the unit was off. Operating unit hours with a value are 24.95 M and without one 0.05 M (0.2%). So the quality column is `operating_nox_missing`, not all missing hours.
- Measurement code: about 75% of the tonnes are "Measured" or "Measured and Substitute" (74.5%); the rest is "Calculated" (from fuel use, 24%), LME, Substitute or no code. `measured_share` is in the annual table so plants that are mostly calculated can be left out of the validation.
- `year` in the PUDL file is the local calendar year (the first hour is 2023-01-01 04:00 UTC), so annual totals are calendar years in the plant's own time zone. Hours are UTC.

## M4.2 The US validation plants

Chosen from the monitors alone, before any satellite estimate exists for a US plant. `validation_set.py` writes `validation_plants.json`, which M4.3 reads. Constants are in `config.yaml` under `validation`.

- Starting point. PLAN.md says to start from the US power plants in the Beirle catalogue. That download (M2.1) is waiting on WDCC approval, so the start is every plant in the EPA hourly file with both years and coordinates (1,298 plants, 733 footprints of plants within 20 km of each other). The ground truth of a footprint is the sum of its monitored plants, the same accounting as the European comparison. When the catalogue arrives it can be used to cross-check the list, not to change it.
- The funnel, with the isolation checks unchanged from candidates.py: 87 footprints of 2,000 t or more in both 2023 and 2024, 57 with good monitors, 40 after `sources`, 33 after `city_near`, 19 after `city_far`, 13 after `hotspot`.
- Good monitors: 90% or more of the tonnes "Measured" (or measured and substitute) in both years, and under 1% of operating unit hours with no NOx value. 30 footprints fail on the measured share (their NOx is mostly calculated from fuel use) and 1 on the gap. Loosening these to 80% and 2% adds 3 footprints and no tier 1 plant, so they do not decide the list.
- 13 is fewer than the 30 to 40 the plan wants. Each check on its own removes 9 to 36 of the 57. Dropping `city_far` and `hotspot` together gives 33, dropping `sources` and `hotspot` gives 30, dropping any one alone gives 14 to 19.
- Two tiers, fixed by the rules and not by any result. Tier 1 (13) passes all four checks and is the population the site would publish. Tier 2 (20) fails only `city_far` and/or `hotspot`, the two checks added after the M3.5 review (the 500,000 of `city_far` is marked provisional in PLAN.md 4.5), and still passes `sources` and `city_near`, the two checks of 4.5 as first written. M4.3 reports tier 1, tier 2 and both pooled, so the validation shows whether the later checks matter, and it is the data V3 needs to set `city_far`.
- Not checked: the coast and terrain flags of PLAN.md 4.5 are not computed, and only power plants have monitors here. A refinery, chemical works or kiln inside the footprint is not in the ground truth. The `hotspot` check is the only guard, and tier 1 has no flag from it. Plants with industry nearby that deserve a look in M4.4 are Midland (MI) in tier 1 and Sabine, R S Nelson and W A Parish on the Gulf coast in tier 2.