# Methods

Pollution Hunter, method `ph-emg-1.2`. Every constant lives in `pipeline/orbyt/modules/pollution_hunter/config.yaml` with its source. This file says what each one is, where it comes from, and what the US validation (milestone M4.4, 15 and 16 November 2026) says about it. The reasoning behind each choice is in `docs/decisions.md`. The validation tables and figures are in `docs/validation/`.

Status: checked against US stack monitors at both wind levels. The estimates use the 500 m wind (section 8) and `u_sys` is 0.40 (section 6). Everything published on the site, Europe and the US test sites, is from `ph-emg-1.2` since 20 November 2026 (section 10).

Changes from `ph-emg-1.1`: the wind level (100 m to 500 m) and `u_sys` (0.35 to 0.40). Nothing else.

## 1. What is estimated

The NOx emission of a subject (a facility, or every register facility within 20 km of it), in tonnes per year expressed as NO2 mass, the same convention as the EU register and the US stack monitors. It is a satellite-based estimate from clear, windy middays (about 13:30 local time). It is not the annual total and it says nothing about permits or compliance.

## 2. Data

| Input | Source | Version or range |
|---|---|---|
| Tropospheric NO2 column | Sentinel-5P TROPOMI, Earth Engine `COPERNICUS/S5P/OFFL/L3_NO2` | July 2022 on (processor 2.4 and later) |
| Wind at the source | ERA5 hourly u and v on pressure levels, Copernicus CDS `reanalysis-era5-pressure-levels`, at the surface pressure minus 55 hPa (about 500 m above ground), interpolated in pressure. Surface pressure from Earth Engine `ECMWF/ERA5/HOURLY`. 0.25 degree cell holding the source, hour nearest the pass | |
| Wind, comparison level | ERA5 hourly 100 m u and v, Earth Engine `ECMWF/ERA5/HOURLY`, same cell and hour. Used up to `ph-emg-1.1` | |
| Reported NOx, EU | EEA Industrial Reporting database | v16 (2007 to 2024) |
| Measured NOx, US | EPA CAMPD hourly stack monitors (CEMS), via PUDL | release v2026.11.0 |
| Unmonitored NOx, US | EPA 2023 National Emissions Inventory, facility summary | 21 July 2026 |

## 3. From images to an emission

| Step | What happens | Constants (config key) | Source |
|---|---|---|---|
| Overpasses | Keep images with solar zenith of 65 degrees or less, sensor zenith of 56 or less, and at least half of a 50 km disc valid | `extract.*` | PLAN.md 4.3 step 2 |
| Patch | 0.03 degree grid, 180 km each way from the source | `extract.grid_step_deg`, `half_extent_km` | PLAN.md 4.3 step 2 |
| Wind | ERA5 wind about 500 m above ground (surface pressure minus 55 hPa) at the hour nearest the pass, worked out from the sun position at the source. Days under 2 m/s are dropped | `wind.level` = 500m, `wind.pressure_levels.offset_hpa` = 55, `wind.min_speed_ms` = 2.0 | PLAN.md 4.3 step 3, M4.4 |
| Rotate | Each day is resampled onto a wind-aligned grid, crosswind -80 to 80 km in 2 km steps, travel time -2 to 6 h in 0.1 h steps, so every day shares one clock | `observe.crosswind_km`, `travel_hours` | PLAN.md Appendix A |
| Background | A tilted plane fitted to the upwind box (20 to 70 km upwind) and both flanks (60 km or more across the wind), clipped at 3 robust sigmas, 3 passes | `observe.upwind_box_km`, `flank_km` = 60 | M3.5, docs/decisions.md |
| Flux | Column above background times wind speed, mol per m per s | | PLAN.md 4.3 step 4 |
| Stack | Mean over days cell by cell, then summed across a fan 20 km wide at the source that widens by 0.3 km per km downwind, capped at 76 km | `fan_half_width()` in core_math.py | PLAN.md Appendix A |
| Fit | Exponentially modified Gaussian: emission q, lifetime tau, blur sigma, plume start t0, residual b. Bounds: tau 0.5 to 12 h, sigma 0.05 to 3 h, t0 -1.5 to 1.5 h | `fit_emg()` | PLAN.md 4.3 step 6 |
| Convert | NOx t/yr = q x 0.0460055 kg/mol x f x c x 31,557,600 s/yr / 1000 | `observe.nox_to_no2` f = 1.38, `observe.amf_correction` c = 1.61 | Beirle et al. 2023 |
| Interval | Days resampled with replacement 200 times, 2.5th and 97.5th percentiles. Sampling noise only | `observe.n_boot` = 200, `seed` = 0 | PLAN.md 4.3 step 8 |

## 4. Quality gates

An estimate that fails any gate is published as inconclusive, never as a number.

| Gate | Passes when | Source |
|---|---|---|
| `too_few_days` | 40 or more days | PLAN.md 4.5 |
| `poor_fit` | r2 of 0.85 or more | PLAN.md 4.5 |
| `source_offset` | abs(t0) of 0.5 h or less | PLAN.md 4.5 |
| `lifetime_out_of_range` | tau from 1 to 8 h | PLAN.md 4.5 |
| `low_signal_to_noise` | estimate at least 3 times (hi - lo) / 3.92 | PLAN.md 4.5 |

Isolation rules for choosing subjects (`candidates.*`): no other register source above 25% of the footprint total 20 to 60 km away, no city of 200,000 within 30 km, no city of 500,000 within 100 km, and no NO2 hotspot 20 to 100 km away above 25% of the subject's own enhancement and 3 robust sigmas of the map.

What the US validation says about the gates (section 7): they separate good estimates from bad ones at both wind levels, and no threshold was changed.

## 5. Conversion constants after validation

- f = 1.38 (Beirle et al. 2023, 1.38 +/- 0.10). Not testable with stack monitors, unchanged.
- c = 1.61 (Beirle et al. 2023, 1.61 +/- 0.32). Unchanged, and used with the 500 m wind, the level of the catalogue it comes from. With the 500 m wind the 7 estimates that pass every gate average 0.91 times the whole footprint at the same hours (V1f, standard error 0.14 in log terms) and 0.93 times it over the calendar year (V2f). The 6 tier 1 estimates average 0.95 times the monitors at the same hours (V1). The 10 tier 1 estimates whose fit and plume start pass at both levels average 0.98 times the footprint (V1f, standard error 0.10). No bias is detectable, so c is not refit (the rule set before the run, section 8). PLAN.md 4.6 says to change c if the estimates come out high against the monitors. They do not.
- c and the wind level cannot be set separately with stack monitors. The emission scales with the wind speed used, and only the product of wind and c is compared with the monitors. The 100 m wind with c = 1.61 reads 0.79 times the footprint on the same 10 estimates (V1f, about 2 standard errors low), so the 100 m wind would need c of about 2.0, outside 1.61 +/- 0.32, fitted to 10 points (section 8).

## 6. Uncertainty and verdict

PLAN.md 4.8, with the systematic term now from the US validation:

```
u_sys   = 0.40                                  # config.yaml verdict.u_sys
s_boot  = (ln(ci_hi) - ln(ci_lo)) / 3.92
s_total = sqrt(s_boot^2 + u_sys^2)
R       = observed / reported_in_footprint
R_lo    = R * exp(-1.96 * s_total)
R_hi    = R * exp(+1.96 * s_total)
```

Where 0.40 comes from, with the 500 m wind: the 7 estimates that pass every gate scatter by 0.41 in ln(estimate / footprint total) for the calendar year (V2f). Their own bootstrap intervals explain 0.20 of that, which leaves 0.36 (tier 1 alone leaves 0.40). That is rounded up to 0.40, the same rule that gave 0.35 from the 100 m excess of 0.33. It is not lowered, because 7 points put the one-sided 95% upper bound of the scatter at about 0.8. 0.35 and 0.40 cannot be told apart with 7 points, so the cautious one is used. The like-for-like comparison (V1f) gives a lower excess, 0.31, as it should: it leaves out the error from seeing only clear middays.

What it means for the verdict. The 500 m estimates that pass every gate have s_boot from 0.16 to 0.25, so s_total is 0.43 to 0.47 and the 95% factor exp(1.96 x s_total) is 2.3 to 2.5. A subject is "higher than reported" only when R_lo > 1.25, so R has to be about 2.9 to 3.2 or more. It is "lower than reported" only when R_hi < 0.80, so R has to be about 0.32 to 0.34 or less. Both need two separate periods (PLAN.md 4.8).

## 7. Validation against US stack monitors

Design (M4.2 and M4.3, fixed before any estimate existed): 33 US power plant footprints, 2023 and 2024, 66 estimates. Tier 1 (13 footprints) passes all four isolation checks and is the population the site would publish. Tier 2 (20) fails only `city_far` and/or the hotspot check.

References:

- V1: the monitor total of the footprint over the 3 whole hours before each pass, on the days the estimate used.
- V2: the calendar-year monitor total.
- V1f and V2f (added in M4.4): the same plus the NOx the monitors cannot see, from the 2023 NEI: every facility within 20 km that is not a power plant, plus any NEI power plant total above CEMS. The satellite sees the whole footprint, and the EU register it is compared with in Europe holds industry too, so this is the like-for-like reference (PLAN.md 4.5). The inventory is annual, so it enters V1f as a flat rate, and 2023 is used for both years.

Results at both wind levels (full tables, including the estimate-by-estimate comparison of the two levels, in `docs/validation/validation_summary.md`). Ratio is the geometric mean of estimate / reference, scatter the standard deviation of its log:

| Set | Reference | 100 m: n, ratio, scatter | 500 m: n, ratio, scatter |
|---|---|---|---|
| Tier 1, all gates passed | V1 | 5, 1.00, 0.33 | 6, 0.95, 0.38 |
| Tier 1, all gates passed | V2f | 5, 0.99, 0.39 | 6, 0.95, 0.44 |
| Both tiers, all gates passed | V1f | 7, 0.85, 0.37 | 7, 0.91, 0.37 |
| Both tiers, all gates passed | V2f | 7, 0.87, 0.40 | 7, 0.93, 0.41 |
| Tier 1, fit and plume start pass at both levels | V1f | 10, 0.79, 0.35 | 10, 0.98, 0.31 |
| Tier 1, every estimate | V1f | 26, median 0.96, 0.65 | 26, median 1.13, 0.86 |
| Tier 2, every estimate | V1f | 40, median 2.25, 0.88 | 40, median 2.45, 1.06 |

Against the PLAN.md 4.9 pass marks, 500 m wind: the bias (ratio of sums) is inside 20% for every gated set (+6% tier 1 against V1, -3% both tiers against V1f). The correlation is 0.83 for tier 1 against V1 and 0.66 for both tiers against V1f, against 0.47 and 0.63 at 100 m. With 6 or 7 points whose references span a factor of about 2.5, a correlation mostly measures noise, so the log scatter is the number to quote, and it is the same at both levels.

The estimates that fail a gate spread more at 500 m (tier 1 scatter 0.65 to 0.86). The gates remove them, which is what they are for, but it is also a reason to repeat the null test at 500 m (section 9).

Why only 7 of 66 pass (the same at both levels):

1. Size. No estimate passes when the footprint total is under 4,000 t (0 of 25). 1 of 20 passes at 4,000 to 6,000 t, and 6 of 21 at 6,000 t or more. On real scenes the practical floor is about 6,000 t, against 2,000 to 4,000 t in the synthetic tests of Appendix A. Most of the US validation plants are below it.
2. Neighbours. Tier 2 fits start the plume downwind of the plant: t0 above 0.5 h in 26 of 40 at 100 m (13 at the 1.5 h bound) and 20 of 40 at 500 m (11 at the bound). A city or industrial area 40 to 90 km away that enters the fan on part of the days adds flux after the source and pushes t0 and q up. Tier 1 has 6 (100 m) and 5 (500 m) of 26 above 0.5 h.
3. The gates fail the right estimates. At 100 m, tier 1 estimates that fail `poor_fit` or `source_offset` read 1.6 times the footprint with a log scatter of 0.74 (two found no plume at all), and at 500 m 1.9 times with 1.10. At 100 m the 3 that fail only `lifetime_out_of_range` read 0.62 times it, because their lifetimes run to 9 to 12 h; at 500 m the same 3 have lifetimes of 7.4 to 7.5 h (the lifetime shrinks with the faster wind) and pass. The 4 estimates that fail only `low_signal_to_noise` (not the same 4 at each level) read 0.80 times the footprint at 100 m and 1.26 times at 500 m. 4 points are too few to change that gate on.

Why tier 2 reads about 3 times its monitors (worked out with the 100 m wind; at 500 m tier 2 reads a median 2.45 times its whole footprint, the same picture):

- Industry inside the footprint, confirmed with the NEI. R S Nelson has 12,600 t of NOx from refineries and chemical plants within 20 km (5.8 times its monitors) and Sabine has 10,300 t (Port Arthur and Beaumont refineries, 3.7 times). Against the whole footprint, R S Nelson 2023 (which passes every gate) goes from 4.1 to 0.69. Midland (tier 1) is flagged too: the NEI lists the Midland Cogeneration Venture at 6,800 short tons, 2,900 t above what CEMS reports for it. W A Parish has almost nothing unmonitored inside 20 km, so its excess comes from Houston, downwind, and not from industry in the footprint.
- Downwind sources, as above. Footprints that fail the hotspot check, alone or with `city_far`, read 2.3 to 2.6 times their whole footprint (geometric mean). The one footprint that fails only `city_far` (J H Campbell, 2 estimates) reads 1.6 times. So the hotspot check is needed, which the null test (M4.5) could not show. `city_far` on its own rests on one footprint and stays provisional. Neither threshold was varied.

Null test (M4.5, V3), 100 m wind: 0 of 20 empty sites pass every gate. Not yet repeated at 500 m.

## 8. Wind level

The 500 m wind is used (`wind.level`), from `ph-emg-1.2`. PLAN.md asks for the 500 m wind (ERA5 pressure levels at surface pressure minus 55 hPa) to be tested against the 100 m wind and the better level kept. Both levels use the same overpasses, the same ERA5 hour and the same cell, so they differ only in height (and in which days fall under the 2 m/s cut). The hourly pressure-level data comes from the Copernicus Climate Data Store as one request per quarter for a box around all the plants (docs/decisions.md). The faster point-optimised ERA5 copies are 6-hourly with only 1000, 925 and 850 hPa near the ground, which would change the wind's timing as well as its height, so they are not used.

What the run of all 33 US plants shows (16 November 2026):

- The 500 m wind is a near-constant multiple of the 100 m wind. Over the days each estimate used, its mean is 1.18 times the 100 m mean (median of 62 estimates with a plume at both levels, range 1.10 to 1.25). The estimates rise by a median of 1.23. 77% move by more than 15%, so the wind level does not meet the V4 mark of PLAN.md 4.9. That is expected: the emission scales with wind speed, so the level is a calibration choice, not noise.
- Because the ratio barely varies, the 500 m wind adds almost no day-to-day information, and the scatter cannot pick the level. The rule set before the run was to keep the level with the lower scatter. On the same estimates the 500 m scatter is lower in every set, but only by 0.02 to 0.04 (0.31 against 0.35 for the 10 tier 1 estimates whose fit and plume start pass at both levels, with a 95% range of the gap of -0.08 to +0.02). On each level's own gated set it is equal or slightly higher. That is a tie.
- So the choice is about wind times c, the one thing stack monitors test. With c = 1.61 the 500 m wind reads 0.91 to 0.98 times the footprint on every set (table in section 7), within one standard error of 1. The 100 m wind looks unbiased only on its own gated set (1.00 for tier 1). On the larger set of 10 it reads 0.79 against the footprint (V1f, standard error 0.11) and 0.87 against the monitors alone (V1). Its gated set looks right because at 100 m the lifetime gate removes three estimates that read low (section 7, point 3).
- c = 1.61 is the air mass factor correction of Beirle et al. (2023), whose catalogue uses wind at about 500 m (PLAN.md 4.3 step 3). The 500 m wind keeps c with the wind it was derived with. Keeping 100 m would need c of about 2.0, outside 1.61 +/- 0.32, fitted to 10 points.
- Tall stacks and plume rise put the gas above 100 m. At Belchatow (300 m stacks, M3.5) the plume drifted to the right of the 100 m wind, as a higher level would explain. At the US plants the 500 m wind turns little (1 degree at Martin Lake), so this does not show in the US numbers.

What did not happen: the 15 November note expected the gated tier 1 estimates to read about 1.2 times the monitors at 500 m and c to need lowering to about 1.34. Each estimate did rise by about 20%, but the set that passes the gates changed. Martin Lake 2023 and 2024 (1.32 and 1.85 times their 100 m estimates) now fail `low_signal_to_noise` (2024 also `source_offset`). Shawnee 2023, New Madrid 2023 and Thomas Hill 2024 now pass, through the lifetime gate. Two of those three read low (about 0.75 and 0.56 times the footprint at the same hours) and one high (about 1.20). So c is not refit: the rule set before the run was to refit c only if the bias at the chosen level was significant, and at 500 m it is not.

The bias shows no dependence on mean wind speed across the tier 1 estimates that do not fail `poor_fit` or `source_offset` (correlation 0.04, 12 estimates, 100 m).

The European subjects got the same 500 m wind from July 2022 to October 2026: one CDS request per quarter for a box around all 15 (18 requests, two and a half to five hours each in the CDS queue). A request over about 10,000 fields is refused, so the Europe box asks for 7 pressure levels (1000 to 850 hPa) rather than 9. Every European target level is 914 hPa or more, so the interpolated wind is the same (`wind.pressure_levels.eu_levels_hpa`).

## 9. Limitations

- One look a day at about 13:30, clear and windy days only, spring to autumn at higher latitudes.
- One average air mass correction instead of a per-pixel one. It is the largest simplification, and it cannot be told apart from a wind-speed error with stack monitors.
- Wind from a 28 km reanalysis grid at a single level, about 500 m above ground. The level is a calibration choice with c (section 8), not a measured plume height.
- The level was chosen on US power plants, all with tall stacks. A low stack on a coast may follow a lower, sea-breeze wind. Melilla (section 10) is the case: its estimate fell to about 0.6 times the 100 m one while its wind barely changed.
- The null test (V3) ran with the 100 m wind and has not been repeated at 500 m. Its European sites sit inside the Europe box, but the two Alpine sites need levels below 850 hPa, and the US sites lie outside the US box.
- Subjects under about 6,000 t/yr rarely pass the gates on real data. They stay candidates (the floor is 2,000 t) but are labelled "below reliable detection" (`candidates.reliable_min_t`, `detection` in findings.json).
- The 13 tier 1 US plants are on the public map as test sites, with the stack monitor total as the record and both years of the comparison in the panel (PLAN.md 1.7 fallback).
- The fan widens to 76 km, so a city or industrial area 40 to 90 km away can enter it. The isolation checks and the plume-start gate guard against this, and the US validation shows they are needed.
- Seven gated US estimates fix u_sys only loosely, at either wind level. More US plants above 6,000 t would tighten it.
- The US unmonitored reference is a single inventory year (2023) and is itself an estimate.

## 10. What the 500 m wind changed in Europe

All 15 European subjects were estimated again with the 500 m wind (20 November 2026). Nothing was chosen from these results: the level, c and u_sys were fixed on US data first (section 8).

| Subject | 100 m: 2023, 2024 (t, gates) | 500 m: 2023, 2024 (t, gates) | 500 m / 100 m wind |
|---|---|---|---|
| Atherinolakkos (register 7,600 both years) | 9,933 pass, 9,124 pass | 12,017 lifetime 0.9 h, 10,519 pass | 1.08 to 1.09 |
| Los Guinchos (3,540, 4,020) | 5,816 pass, 6,055 pass | 5,718 pass, 5,838 pass | 1.00 to 1.02 |
| Melilla (3,100, no 2024 row) | 8,115 pass, 8,273 pass | 4,960 lifetime 9.9 h, 4,694 pass | 1.03 to 1.04 |
| Tornio (2,001, 2,353) | 4,373 pass, fails | 6,053 pass, fails | 1.23 |
| The other 11 | fail both years | fail both years | 0.96 to 1.27 |

- Verdicts: 2, both "consistent with reported", grade C. Atherinolakkos 2024: 10,519 t against 7,600, ratio 1.38 (0.62 to 3.08). Los Guinchos 2024: 5,838 t against 4,020, ratio 1.45 (0.65 to 3.24). With the 100 m wind there were 3. Melilla lost its verdict: its 2023 estimate now fails the lifetime gate, and 2024, which passes, has no register value to compare with.
- The 500 m wind is closer to the 100 m wind over the sea and the islands than at the US plants (1.00 to 1.09 at Los Guinchos, Melilla, Atherinolakkos and Thira, against 1.18 in the US). In Poland, Denmark and the north it is 1.15 to 1.27.
- Melilla changed shape, not scale. Its wind is only 3 to 4% faster at 500 m and turns by a median of 8 degrees (more than 30 degrees on 11% of days), yet its lifetime went from about 2 h to 6 to 10 h and its estimate fell to 0.57 to 0.61 times. A diesel plant on a coast, probably with far lower stacks than the US coal plants, is the case a 500 m wind fits least (section 9). It is reported, not corrected: changing the level for one site after seeing its result would be tuning on Europe.
- Rolling 12-month windows that pass every gate, 100 m then 500 m: Atherinolakkos 27 and 22 of 41, Los Guinchos 35 and 35, Melilla 41 and 31, Tornio 8 and 8 of 39, Maritsa East 2 5 and 4. The rest have none at either level.
- US test sites on the map: New Madrid 2024, Shawnee 2023, Gerald Gentleman 2023 and Thomas Hill 2024 carry an estimate. Martin Lake no longer does (it fails a gate in both years at 500 m).
