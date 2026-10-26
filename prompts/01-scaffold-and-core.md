# 01: Scaffold and core logic

**Read first:** PRD sections 5, 6 (FR-1, FR-2), 7 and 11.

## Task
1. Initialize the project: `pyproject.toml` (package `flake_detector` in `src/`, console script `flake = flake_detector.cli:app`), `.gitignore` (Python, `.env`, `results/`, caches), `.env.example` (`GROQ_API_KEY=`, `GROQ_MODEL=`), `LICENSE` (MIT), minimal `README.md` placeholder, ruff and pytest config. Dependencies as listed in PRD section 11.
2. `models.py`: Pydantic v2 models for `Task`, `GraderSpec`, `Suite`, `AgentOutput`, `RunRecord`, `TaskResult`, `RunResults` matching the results JSON in PRD section 7.
3. `metrics.py`: pure functions with no I/O:
   - `wilson_interval(c, n, z=1.96)`
   - `pass_at_k(n, c, k)` and `pass_hat_k(n, c, k)` using exact combinatorics (`math.comb`), handling edge cases from the PRD
   - `flakiness(c, n)` and `task_status(c, n)`
   - `suite_summary(task_results, k)` and `pass_curves(task_results, max_k)`
4. `grading.py`: `exact`, `contains`, `regex`, `numeric` graders returning success plus `failure_reason`. Numeric grading must extract the first number from messy text like "The answer is 391." before comparing.
5. `suite.py`: load and validate a YAML suite, with friendly errors that name the file and task id. Compute `sha256_12` of the file bytes.
6. Add `suites/demo_sim.yaml`: 12 tasks across at least 3 categories with varied `sim.p_success` (a few near 1.0, a few near 0.5, one near 0.1) so the report shows consistent, flaky and failing tasks.

## Tests (write them now)
- `test_metrics.py`: every test vector from PRD section 5, plus property checks (`0 <= pass^k <= pass@k <= 1`, interval contains `p`).
- `test_grading.py`: each grader, including messy numeric text and each failure reason.
- `test_suite.py`: valid suite loads; duplicate task ids, unknown grader type and missing fields give clear errors.

## Done when
`pytest` and `ruff check .` pass and all PRD test vectors match to 1e-3. Commit, summarize, then wait for "next".
