# Validation against US stack monitors (M4.3)

Pass marks (PLAN.md 4.9, V1): mean bias within 20 percent and correlation above 0.7.
Bias is the ratio of sums minus one. Scatter is the standard deviation of ln(estimate / monitor).

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

## Flagged for possible unmonitored industry

The monitor total is the sum of CEMS power plants. Refineries, chemical plants and other industry beside these plants report nothing to CEMS, so a satellite estimate above the monitors may be real emissions that the monitors cannot see: Midland Cogeneration Venture, R S Nelson, Sabine, W A Parish.
