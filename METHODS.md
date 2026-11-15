# Methods

Pollution Hunter, method `ph-emg-1.1`. Every constant lives in `pipeline/orbyt/modules/pollution_hunter/config.yaml` with its source. This file says what each one is, where it comes from, and what the US validation (milestone M4.4, 15 November 2026) says about it. The reasoning behind each choice is in `docs/decisions.md`. The validation tables and figure are in `docs/validation/`.

Status: checked against US stack monitors with the 100 m wind. The 500 m wind test (PLAN.md 4.3 step 3, V4) has not finished, see "Wind level" below.

## 1. What is estimated

The NOx emission of a subject (a facility, or every register facility within 20 km of it), in tonnes per year expressed as NO2 mass, the same convention as the EU register and the US stack monitors. It is a satellite-based estimate from clear, windy middays (about 13:30 local time). It is not the annual total and it says nothing about permits or compliance.

## 2. Data

| Input | Source | Version or range |
|---|---|---|
| Tropospheric NO2 column | Sentinel-5P TROPOMI, Earth Engine `COPERNICUS/S5P/OFFL/L3_NO2` | July 2022 on (processor 2.4 and later) |
| Wind at the source | ERA5 hourly 100 m u and v, Earth Engine `ECMWF/ERA5/HOURLY`, 0.25 degree cell holding the source, hour nearest the pass | |
| Reported NOx, EU | EEA Industrial Reporting database | v16 (2007 to 2024) |
| Measured NOx, US | EPA CAMPD hourly stack monitors (CEMS), via PUDL | release v2026.11.0 |
| Unmonitored NOx, US | EPA 2023 National Emissions Inventory, facility summary | 21 July 2026 |

## 3. From images to an emission

| Step | What happens | Constants (config key) | Source |
|---|---|---|---|
| Overpasses | Keep images with solar zenith of 65 degrees or less, sensor zenith of 56 or less, and at least half of a 50 km disc valid | `extract.*` | PLAN.md 4.3 step 2 |
| Patch | 0.03 degree grid, 180 km each way from the source | `extract.grid_step_deg`, `half_extent_km` | PLAN.md 4.3 step 2 |
| Wind | 100 m ERA5 wind at the hour nearest the pass, worked out from the sun position at the source. Days under 2 m/s are dropped | `wind.min_speed_ms` = 2.0 | PLAN.md 4.3 step 3 |
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

What the US validation says about the gates (section 7): they separate good estimates from bad ones, and no threshold was changed.

## 5. Conversion constants after validation

- f = 1.38 (Beirle et al. 2023, 1.38 +/- 0.10). Not testable with stack monitors, unchanged.
- c = 1.61 (Beirle et al. 2023, 1.61 +/- 0.32). Unchanged. With the 100 m wind the 5 tier 1 estimates that pass every gate average 1.00 times the monitors at the same hours (V1) and 0.99 times the whole footprint over the calendar year (V2f). All 7 passing estimates average 0.87 times the footprint (V2f). With 7 points and a log scatter of 0.40, the uncertainty on that mean is about +/- 30%, so no bias is detectable and there is no basis for a different c. PLAN.md 4.6 says to change c if the estimates come out high against the monitors. They do not.
- c and the wind level cannot be set separately with stack monitors. The emission scales with the wind speed used, and only the product of wind and c is compared with the monitors. If the 500 m wind is adopted, c must be refit with it (section 8).

## 6. Uncertainty and verdict

PLAN.md 4.8, with the systematic term now from the US validation:

```
u_sys   = 0.35                                  # config.yaml verdict.u_sys
s_boot  = (ln(ci_hi) - ln(ci_lo)) / 3.92
s_total = sqrt(s_boot^2 + u_sys^2)
R       = observed / reported_in_footprint
R_lo    = R * exp(-1.96 * s_total)
R_hi    = R * exp(+1.96 * s_total)
```

Where 0.35 comes from: the 7 estimates that pass every gate scatter by 0.40 in ln(estimate / footprint total) for the calendar year (V2f). Their own bootstrap intervals explain 0.22 of that, which leaves 0.33 (tier 1 alone gives the same, 0.33). That is rounded up to 0.35, which is also the plan's placeholder. It is not lowered further, because 7 points put the one-sided 95% upper bound of the scatter at about 0.8. The like-for-like comparison (V1f) gives a lower excess, 0.29, as it should: it leaves out the error from seeing only clear middays.

What it means for the verdict. The estimates that pass every gate have s_boot from 0.10 to 0.24, so s_total is 0.36 to 0.42 and the 95% factor exp(1.96 x s_total) is 2.0 to 2.3. A subject is "higher than reported" only when R_lo > 1.25, so R has to be about 2.5 to 2.8 or more. It is "lower than reported" only when R_hi < 0.80, so R has to be about 0.35 to 0.39 or less. Both need two separate periods (PLAN.md 4.8).

## 7. Validation against US stack monitors

Design (M4.2 and M4.3, fixed before any estimate existed): 33 US power plant footprints, 2023 and 2024, 66 estimates. Tier 1 (13 footprints) passes all four isolation checks and is the population the site would publish. Tier 2 (20) fails only `city_far` and/or the hotspot check.

References:

- V1: the monitor total of the footprint over the 3 whole hours before each pass, on the days the estimate used.
- V2: the calendar-year monitor total.
- V1f and V2f (added in M4.4): the same plus the NOx the monitors cannot see, from the 2023 NEI: every facility within 20 km that is not a power plant, plus any NEI power plant total above CEMS. The satellite sees the whole footprint, and the EU register it is compared with in Europe holds industry too, so this is the like-for-like reference (PLAN.md 4.5). The inventory is annual, so it enters V1f as a flat rate, and 2023 is used for both years.

Results, 100 m wind (full tables in `docs/validation/validation_summary.md`):

| Set | n | Ratio (geometric mean) | Log scatter | Bias (ratio of sums) |
|---|---|---|---|---|
| Tier 1, all gates passed, V1 | 5 | 1.00 | 0.33 | +5% |
| Tier 1, all gates passed, V2f | 5 | 0.99 | 0.39 | +3% |
| Both tiers, all gates passed, V1f | 7 | 0.85 | 0.37 | -10% |
| Both tiers, all gates passed, V2f | 7 | 0.87 | 0.40 | -9% |
| Tier 1, every estimate, V1f | 26 | median 0.96 | 0.65 | +25% |
| Tier 2, every estimate, V1f | 40 | median 2.25 | 0.88 | +206% |

Against the PLAN.md 4.9 pass marks: the bias is inside 20% for the gated estimates. The correlation (0.47 for tier 1 against V1, 0.63 for both tiers against V1f) misses 0.7. With 5 to 7 points whose references span a factor of about 2.5, a correlation mostly measures noise, so the log scatter is the number to quote.

Why only 7 of 66 pass:

1. Size. No estimate passes when the footprint total is under 4,000 t (0 of 25). 1 of 20 passes at 4,000 to 6,000 t, and 6 of 21 at 6,000 t or more (5 of 10 in tier 1). On real scenes the practical floor is about 6,000 t, against 2,000 to 4,000 t in the synthetic tests of Appendix A. Most of the US validation plants are below it.
2. Neighbours. Tier 2 fits start the plume downwind of the plant: t0 above 0.5 h in 26 of 40 (13 at the 1.5 h bound) and never below -0.5 h. A city or industrial area 40 to 90 km away that enters the fan on part of the days adds flux after the source and pushes t0 and q up. Tier 1 has 6 of 26 above 0.5 h.
3. The gates fail the right estimates. Tier 1 estimates that fail `poor_fit` or `source_offset` read 1.6 times the footprint with a log scatter of 0.74 (two found no plume at all). The 3 that fail only `lifetime_out_of_range` read 0.62 times it. The 4 that fail only `low_signal_to_noise` read 0.80 times it with a scatter of 0.20, so that gate may be stricter than it needs to be, but 4 points are too few to change it on.

Why tier 2 reads about 3 times its monitors:

- Industry inside the footprint, confirmed with the NEI. R S Nelson has 12,600 t of NOx from refineries and chemical plants within 20 km (5.8 times its monitors) and Sabine has 10,300 t (Port Arthur and Beaumont refineries, 3.7 times). Against the whole footprint, R S Nelson 2023 (which passes every gate) goes from 4.1 to 0.69. Midland (tier 1) is flagged too: the NEI lists the Midland Cogeneration Venture at 6,800 short tons, 2,900 t above what CEMS reports for it. W A Parish has almost nothing unmonitored inside 20 km, so its excess comes from Houston, downwind, and not from industry in the footprint.
- Downwind sources, as above. Footprints that fail the hotspot check, alone or with `city_far`, read 2.3 to 2.6 times their whole footprint (geometric mean). The one footprint that fails only `city_far` (J H Campbell, 2 estimates) reads 1.6 times. So the hotspot check is needed, which the null test (M4.5) could not show. `city_far` on its own rests on one footprint and stays provisional. Neither threshold was varied.

Null test (M4.5, V3): 0 of 20 empty sites pass every gate.

## 8. Wind level

The 100 m wind is used. PLAN.md asks for the 500 m wind (ERA5 pressure levels at surface pressure minus 55 hPa) to be tested and the better level kept. That run reads from the Copernicus Climate Data Store one quarter at a time and has been held up for days by the store's queue limit. On 15 November 2026 it had finished one plant-year: Martin Lake 2023, where the 500 m wind at the overpass hours is 1.21 times the 100 m wind (median of 140 days, 1.23 as a ratio of means) and turns by only 1 degree.

What that implies, to be confirmed when the run finishes: the estimates would rise by about 20%, the gated tier 1 estimates would read about 1.2 times their monitors, and keeping them unbiased would need c of about 1.34, which is inside the published 1.61 +/- 0.32. The level is to be chosen by the lower scatter against the monitors (V4), and c refit at that level only if the bias is significant. The bias shows no dependence on mean wind speed across the tier 1 estimates that do not fail `poor_fit` or `source_offset` (correlation 0.04, 12 estimates).

## 9. Limitations

- One look a day at about 13:30, clear and windy days only, spring to autumn at higher latitudes.
- One average air mass correction instead of a per-pixel one. It is the largest simplification, and it cannot be told apart from a wind-speed error with stack monitors.
- Wind from a 28 km reanalysis grid at a single level.
- Subjects under about 6,000 t/yr rarely pass the gates on real data.
- The fan widens to 76 km, so a city or industrial area 40 to 90 km away can enter it. The isolation checks and the plume-start gate guard against this, and the US validation shows they are needed.
- Seven gated US estimates fix u_sys only loosely. More US plants above 6,000 t, or the 500 m wind run, will tighten it.
- The US unmonitored reference is a single inventory year (2023) and is itself an estimate.
