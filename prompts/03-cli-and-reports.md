# 03: CLI, reports, charts and compare

**Read first:** PRD sections 6 (FR-7, FR-8, FR-11), 8 and 9.

## Task
1. `report.py`: build the Markdown report with the five sections in PRD section 9. Per-task table sorted by flakiness descending, with status shown as plain words (`consistent`, `flaky`, `failing`). Write short, plain-language notes under the summary explaining `pass@k` vs `pass^k`. State the number of runs per task and warn when `n < 10` that intervals are wide.
2. Charts with Matplotlib using the `Agg` backend:
   - `pass_curves.png`: mean `pass@k` and `pass^k` for `k = 1..K`, labeled axes, legend, shaded gap between the lines.
   - `task_rates.png`: horizontal bars of success rate per task with Wilson error bars, sorted.
   Clean style, readable at README width, colorblind-safe palette, deterministic file names.
3. `compare.py`:
   - per-task comparison using non-overlapping Wilson intervals
   - suite-level paired bootstrap over tasks (1000 resamples, fixed seed) on the difference in mean success rate with a 95% percentile interval
   - a Markdown comparison report listing improved, regressed and unchanged tasks, and the verdict
   - only tasks present in both runs are compared; list tasks present in only one and say so
4. `cli.py` with Typer exactly as in PRD section 8: `run`, `report`, `compare`. Use Rich for a progress bar and tidy tables. Validation errors exit with code 2 and a clear message. `compare --fail-on-regression` exits 1 only on a regression.
5. Generate sample outputs and commit them under `examples/`: run the simulated demo suite (`--runs 20 --k 5 --seed 42`), save `sample_results.json`, `sample_report.md` and the charts. Also create a degraded copy of the suite (lower `p_success` on several tasks) as `suites/demo_sim_degraded.yaml` to demonstrate `compare`.

## Tests
- Report contains every task id and all five sections; charts are created and non-empty.
- `compare`: identical runs give no regression and exit code 0; the degraded run gives a regression and exit code 1 with `--fail-on-regression`; without the flag the exit code is 0.
- CLI argument validation (`k > runs`, missing file) exits with code 2.

## Done when
The acceptance criteria 1 to 4 in the PRD pass by hand. Commit, summarize, then wait for "next".
