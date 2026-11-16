# Validation against US stack monitors (M4.3, M4.4)

Pass marks (PLAN.md 4.9, V1): mean bias within 20 percent and correlation above 0.7.
Bias is the ratio of sums minus one. Scatter is the standard deviation of ln(estimate / reference).

References: V1 monitors, 3 h before each pass; V2 monitors, calendar year; V1f footprint (monitors + NEI unmonitored), 3 h before each pass; V2f footprint (monitors + NEI unmonitored), calendar year. The unmonitored NOx is from EPA 2023 National Emissions Inventory, facility summary (21 July 2026), used for both years.

## Gates, wind 100m

Times each gate failed, in all and alone (the only gate that failed).

| tier | n | passed | too_few_days | poor_fit | source_offset | lifetime_out_of_range | low_signal_to_noise |
|---|---|---|---|---|---|---|---|
| 1 | 26 | 5 | 0 (0) | 12 (0) | 9 (0) | 12 (3) | 17 (4) |
| 2 | 40 | 2 | 0 (0) | 13 (0) | 26 (4) | 19 (0) | 29 (3) |

Passes by footprint size (calendar-year monitors + NEI unmonitored):

| footprint t/yr | tier | n | passed |
|---|---|---|---|
| 0 to 4,000 | 1 | 7 | 0 |
| 0 to 4,000 | 2 | 18 | 0 |
| 4,000 to 6,000 | 1 | 9 | 0 |
| 4,000 to 6,000 | 2 | 11 | 1 |
| 6,000+ | 1 | 10 | 5 |
| 6,000+ | 2 | 11 | 1 |

Systematic scatter of the estimates that pass every gate (u_sys, PLAN.md 4.8): observed log scatter, the part the bootstrap explains, the excess, and the one-sided 95% upper bound of the observed scatter.

| comparison | group | n | mean ratio | observed | bootstrap | excess | upper 95% |
|---|---|---|---|---|---|---|---|
| V1 | tier 1 | 5 | 1.00 | 0.33 | 0.22 | 0.24 | 0.78 |
| V1 | pooled | 7 | 1.12 | 0.67 | 0.22 | 0.64 | 1.29 |
| V2 | tier 1 | 5 | 1.00 | 0.40 | 0.22 | 0.33 | 0.95 |
| V2 | pooled | 7 | 1.15 | 0.73 | 0.22 | 0.70 | 1.40 |
| V1f | tier 1 | 5 | 0.98 | 0.32 | 0.22 | 0.24 | 0.76 |
| V1f | pooled | 7 | 0.85 | 0.37 | 0.22 | 0.29 | 0.70 |
| V2f | tier 1 | 5 | 0.99 | 0.39 | 0.22 | 0.33 | 0.94 |
| V2f | pooled | 7 | 0.87 | 0.40 | 0.22 | 0.33 | 0.76 |

## Gates, wind 500m

Times each gate failed, in all and alone (the only gate that failed).

| tier | n | passed | too_few_days | poor_fit | source_offset | lifetime_out_of_range | low_signal_to_noise |
|---|---|---|---|---|---|---|---|
| 1 | 26 | 6 | 0 (0) | 12 (0) | 6 (0) | 12 (0) | 19 (4) |
| 2 | 40 | 1 | 0 (0) | 15 (1) | 22 (5) | 16 (0) | 27 (4) |

Passes by footprint size (calendar-year monitors + NEI unmonitored):

| footprint t/yr | tier | n | passed |
|---|---|---|---|
| 0 to 4,000 | 1 | 7 | 0 |
| 0 to 4,000 | 2 | 18 | 0 |
| 4,000 to 6,000 | 1 | 9 | 1 |
| 4,000 to 6,000 | 2 | 11 | 0 |
| 6,000+ | 1 | 10 | 5 |
| 6,000+ | 2 | 11 | 1 |

Systematic scatter of the estimates that pass every gate (u_sys, PLAN.md 4.8): observed log scatter, the part the bootstrap explains, the excess, and the one-sided 95% upper bound of the observed scatter.

| comparison | group | n | mean ratio | observed | bootstrap | excess | upper 95% |
|---|---|---|---|---|---|---|---|
| V1 | tier 1 | 6 | 0.95 | 0.38 | 0.20 | 0.33 | 0.80 |
| V1 | pooled | 7 | 1.20 | 0.70 | 0.20 | 0.67 | 1.34 |
| V2 | tier 1 | 6 | 0.97 | 0.44 | 0.20 | 0.39 | 0.91 |
| V2 | pooled | 7 | 1.24 | 0.76 | 0.20 | 0.74 | 1.46 |
| V1f | tier 1 | 6 | 0.93 | 0.39 | 0.20 | 0.34 | 0.82 |
| V1f | pooled | 7 | 0.91 | 0.37 | 0.20 | 0.31 | 0.70 |
| V2f | tier 1 | 6 | 0.95 | 0.44 | 0.20 | 0.40 | 0.93 |
| V2f | pooled | 7 | 0.93 | 0.41 | 0.20 | 0.36 | 0.79 |

## Wind 100m against 500m

62 estimates find a plume at both levels. Mean wind over the days used, 500m / 100m: median 1.18, range 1.10 to 1.25. Estimate 500m / 100m: median 1.23, geometric mean 1.27; 77% move by more than 15% (V4 pass mark).

Passing every gate at each level:

| tier | both | 100m only | 500m only | neither |
|---|---|---|---|---|
| 1 | 3 | 2 | 3 | 18 |
| 2 | 1 | 1 | 0 | 38 |

Geometric mean ratio (standard error in log units), log scatter and Pearson r, on the same estimates at both levels, and on each level's own set of estimates that pass every gate:

| set | reference | n | 100m ratio (se) | scatter | r | 500m ratio (se) | scatter | r |
|---|---|---|---|---|---|---|---|---|
| passes at both, tier 1 | V1 | 3 | 0.94 (0.25) | 0.44 | 0.57 | 1.10 (0.23) | 0.40 | 0.55 |
| passes at both, pooled | V1 | 4 | 1.36 (0.41) | 0.82 | -0.25 | 1.58 (0.40) | 0.80 | -0.27 |
| fit and plume start pass at both, tier 1 | V1 | 10 | 0.87 (0.13) | 0.41 | 0.67 | 1.08 (0.11) | 0.34 | 0.77 |
| own gated set, tier 1 | V1 | 5 and 6 | 1.00 (0.15) | 0.33 | 0.47 | 0.95 (0.16) | 0.38 | 0.83 |
| own gated set, pooled | V1 | 7 and 7 | 1.12 (0.25) | 0.67 | 0.18 | 1.20 (0.26) | 0.70 | 0.13 |
| passes at both, tier 1 | V1f | 3 | 0.94 (0.25) | 0.44 | 0.57 | 1.10 (0.23) | 0.40 | 0.55 |
| passes at both, pooled | V1f | 4 | 0.86 (0.20) | 0.40 | 0.45 | 1.01 (0.18) | 0.37 | 0.48 |
| fit and plume start pass at both, tier 1 | V1f | 10 | 0.79 (0.11) | 0.35 | 0.81 | 0.98 (0.10) | 0.31 | 0.84 |
| own gated set, tier 1 | V1f | 5 and 6 | 0.98 (0.14) | 0.32 | 0.48 | 0.93 (0.16) | 0.39 | 0.82 |
| own gated set, pooled | V1f | 7 and 7 | 0.85 (0.14) | 0.37 | 0.63 | 0.91 (0.14) | 0.37 | 0.66 |
| passes at both, tier 1 | V2f | 3 | 0.95 (0.32) | 0.55 | -0.18 | 1.11 (0.30) | 0.52 | -0.24 |
| passes at both, pooled | V2f | 4 | 0.88 (0.24) | 0.48 | 0.29 | 1.02 (0.23) | 0.46 | 0.30 |
| fit and plume start pass at both, tier 1 | V2f | 10 | 0.81 (0.12) | 0.38 | 0.62 | 1.01 (0.11) | 0.35 | 0.65 |
| own gated set, tier 1 | V2f | 5 and 6 | 0.99 (0.18) | 0.39 | 0.00 | 0.95 (0.18) | 0.44 | 0.51 |
| own gated set, pooled | V2f | 7 and 7 | 0.87 (0.15) | 0.40 | 0.55 | 0.93 (0.16) | 0.41 | 0.57 |

## V1, wind 100m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 36 | 1.06 | 0.19 | 0.47 | 0.65 | 2 |
| tier 1 | gates passed | 5 | 5 | 1.01 | 0.47 | 0.50 | 0.33 | 0 |
| tier 2 | all | 40 | 300 | 2.76 | 0.35 | 0.33 | 0.88 | 2 |
| tier 2 | gates passed | 2 | 75 | 2.31 |  |  |  |  |
| pooled | all | 66 | 184 | 1.86 | 0.16 | 0.27 | 0.90 | 4 |
| pooled | gates passed | 7 | 15 | 1.01 | 0.18 | 0.21 | 0.67 | 0 |

## V2, wind 100m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 39 | 1.10 | 0.18 | 0.49 | 0.65 | 2 |
| tier 1 | gates passed | 5 | 4 | 1.04 | -0.03 | -0.30 | 0.40 | 0 |
| tier 2 | all | 40 | 316 | 2.96 | 0.35 | 0.32 | 0.89 | 2 |
| tier 2 | gates passed | 2 | 91 | 2.63 |  |  |  |  |
| pooled | all | 66 | 194 | 1.87 | 0.15 | 0.26 | 0.91 | 4 |
| pooled | gates passed | 7 | 17 | 1.04 | 0.08 | -0.14 | 0.73 | 0 |

## V1f, wind 100m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 25 | 0.96 | 0.18 | 0.43 | 0.65 | 2 |
| tier 1 | gates passed | 5 | 3 | 0.98 | 0.48 | 0.50 | 0.32 | 0 |
| tier 2 | all | 40 | 206 | 2.25 | 0.18 | 0.47 | 0.88 | 2 |
| tier 2 | gates passed | 2 | -36 | 0.60 |  |  |  |  |
| pooled | all | 66 | 135 | 1.67 | 0.17 | 0.36 | 0.87 | 4 |
| pooled | gates passed | 7 | -10 | 0.93 | 0.63 | 0.71 | 0.37 | 0 |

## V2f, wind 100m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 28 | 0.97 | 0.17 | 0.40 | 0.65 | 2 |
| tier 1 | gates passed | 5 | 3 | 1.01 | 0.00 | -0.30 | 0.39 | 0 |
| tier 2 | all | 40 | 216 | 2.30 | 0.19 | 0.47 | 0.89 | 2 |
| tier 2 | gates passed | 2 | -34 | 0.63 |  |  |  |  |
| pooled | all | 66 | 142 | 1.74 | 0.17 | 0.36 | 0.88 | 4 |
| pooled | gates passed | 7 | -9 | 0.82 | 0.55 | 0.36 | 0.40 | 0 |

## V1, wind 500m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 101 | 1.24 | 0.03 | 0.35 | 0.84 | 1 |
| tier 1 | gates passed | 6 | 6 | 0.94 | 0.83 | 0.83 | 0.38 | 0 |
| tier 2 | all | 40 | 486 | 4.10 | 0.42 | 0.50 | 1.05 | 2 |
| tier 2 | gates passed | 1 | 372 | 4.72 |  |  |  |  |
| pooled | all | 66 | 318 | 2.17 | 0.18 | 0.35 | 1.05 | 3 |
| pooled | gates passed | 7 | 26 | 1.04 | 0.13 | 0.29 | 0.70 | 0 |

## V2, wind 500m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 107 | 1.21 | -0.02 | 0.33 | 0.88 | 1 |
| tier 1 | gates passed | 6 | 7 | 0.91 | 0.53 | 0.60 | 0.44 | 0 |
| tier 2 | all | 40 | 511 | 4.32 | 0.45 | 0.46 | 1.06 | 2 |
| tier 2 | gates passed | 1 | 442 | 5.42 |  |  |  |  |
| pooled | all | 66 | 333 | 2.32 | 0.19 | 0.31 | 1.07 | 3 |
| pooled | gates passed | 7 | 28 | 0.92 | 0.01 | 0.11 | 0.76 | 0 |

## V1f, wind 500m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 85 | 1.13 | -0.01 | 0.31 | 0.86 | 1 |
| tier 1 | gates passed | 6 | 4 | 0.90 | 0.82 | 0.77 | 0.39 | 0 |
| tier 2 | all | 40 | 349 | 2.45 | 0.14 | 0.53 | 1.06 | 2 |
| tier 2 | gates passed | 1 | -22 | 0.78 |  |  |  |  |
| pooled | all | 66 | 246 | 1.92 | 0.12 | 0.39 | 1.04 | 3 |
| pooled | gates passed | 7 | -3 | 0.78 | 0.66 | 0.75 | 0.37 | 0 |

## V2f, wind 500m

| group | subset | n | bias % | median ratio | Pearson r | Spearman r | log scatter | no plume |
|---|---|---|---|---|---|---|---|---|
| tier 1 | all | 26 | 90 | 1.12 | -0.06 | 0.27 | 0.89 | 1 |
| tier 1 | gates passed | 6 | 5 | 0.85 | 0.51 | 0.60 | 0.44 | 0 |
| tier 2 | all | 40 | 363 | 2.62 | 0.16 | 0.49 | 1.06 | 2 |
| tier 2 | gates passed | 1 | -20 | 0.80 |  |  |  |  |
| pooled | all | 66 | 256 | 2.00 | 0.12 | 0.36 | 1.06 | 3 |
| pooled | gates passed | 7 | -1 | 0.80 | 0.57 | 0.61 | 0.41 | 0 |

## Footprints with unmonitored NOx

The monitor total is the sum of CEMS power plants. Refineries, chemical plants and other industry report nothing to CEMS. A footprint is flagged when the NEI lists unmonitored NOx of at least 25% of the monitor total within the footprint.

| footprint | tier | monitors 2023 t | NEI unmonitored t | largest sources |
|---|---|---|---|---|
| Midland Cogeneration Venture | 1 | 3,240 | 3,120 | NEI power plants above CEMS 2941 t |
| Sabine | 2 | 2,799 | 10,253 | PORT ARTHUR REFINERY 1607 t; BEAUMONT REFINERY 1493 t; ORANGE SITE 1422 t |
| R S Nelson | 2 | 2,180 | 12,648 | Westlake US 2 LLC - Westlake Lake Charles South 3962 t; CITGO Petroleum Corp - Lake Charles Manufacturing Complex 3224 t; Sasol Chemicals (USA) LLC - Lake Charles Chemical Complex 1234 t |
