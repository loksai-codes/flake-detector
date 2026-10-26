# Flake Detector Report: `demo-sim`

## 1. Run Metadata
- **Agent:** `sim`
- **Suite:** `demo-sim` (SHA-256: `f3b1e6e679aa`)
- **Parameters:** `runs=20`, `k=5`, `seed=42`
- **Created At:** 2026-10-26T06:58:22.244571+00:00
- **Run ID:** `2026-10-26T06-58-22_demo-sim_sim`

## 2. Suite Summary
- **Mean pass@1 (Success Rate):** 0.5625 (56.2%)
- **Mean pass^5 (All 5 Succeed):** 0.3203 (32.0%)
- **Mean pass@5 (At least 1 Succeeds):** 0.8549 (85.5%)
- **Task Distribution:** 25.0% consistent (3), 66.7% flaky (8), 8.3% failing (1)
- **Mean Latency:** 433.4 ms
- **Total Tokens:** 12,571 (in: 8,307, out: 4,264)

> **Understanding `pass@k` vs `pass^k`:**
> `pass@5` is the probability that *at least one* out of 5 attempts succeeds (optimistic capability).
> `pass^5` is the probability that *all* 5 attempts succeed without failure (true dependability).
> The difference between them represents the agent's flakiness gap.

## 3. Per-Task Consistency
| Task ID | Category | Runs (n) | Passes (c) | Success Rate | 95% CI (Wilson) | pass@k | pass^k | Status |
|:---|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| `math-div-01` | math | 20 | 10 | 0.500 | [0.299, 0.701] | 0.984 | 0.016 | `flaky` |
| `format-json-01` | formatting | 20 | 10 | 0.500 | [0.299, 0.701] | 0.984 | 0.016 | `flaky` |
| `reason-capital-01` | reasoning | 20 | 9 | 0.450 | [0.258, 0.658] | 0.970 | 0.008 | `flaky` |
| `math-sqrt-01` | math | 20 | 12 | 0.600 | [0.387, 0.781] | 0.996 | 0.051 | `flaky` |
| `format-slug-01` | formatting | 20 | 7 | 0.350 | [0.181, 0.567] | 0.917 | 0.001 | `flaky` |
| `reason-logic-01` | reasoning | 20 | 5 | 0.250 | [0.112, 0.469] | 0.806 | 0.000 | `flaky` |
| `math-power-01` | math | 20 | 3 | 0.150 | [0.052, 0.360] | 0.601 | 0.000 | `flaky` |
| `math-add-01` | math | 20 | 19 | 0.950 | [0.764, 0.991] | 1.000 | 0.750 | `flaky` |
| `reason-trick-01` | reasoning | 20 | 0 | 0.000 | [0.000, 0.161] | 0.000 | 0.000 | `failing` |
| `math-mult-01` | math | 20 | 20 | 1.000 | [0.839, 1.000] | 1.000 | 1.000 | `consistent` |
| `format-upper-01` | formatting | 20 | 20 | 1.000 | [0.839, 1.000] | 1.000 | 1.000 | `consistent` |
| `format-contains-01` | formatting | 20 | 20 | 1.000 | [0.839, 1.000] | 1.000 | 1.000 | `consistent` |

## 4. Failure Reasons Breakdown
| Failure Reason | Count | Percentage |
|:---|:---:|:---:|
| `wrong_answer` | 75 | 71.4% |
| `tool_error` | 10 | 9.5% |
| `format_error` | 7 | 6.7% |
| `no_answer` | 7 | 6.7% |
| `exception` | 6 | 5.7% |

## 5. Consistency Charts
![Pass Curves](examples/charts/pass_curves.png)

![Task Rates](examples/charts/task_rates.png)
