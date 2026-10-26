# 02: Runner and simulated agent

**Read first:** PRD sections 6 (FR-3 to FR-6, FR-9), 7 and 10 (simulated agent).

## Task
1. `agents/base.py`: an `Agent` Protocol with `name`, `config` (dict, no secrets) and `run(task, seed) -> AgentOutput`.
2. `agents/simulated.py`: the simulated agent exactly as in PRD section 10.
   - Seed a private `random.Random` from a stable hash (`hashlib`) of `(seed, task_id, run_index)`. Never use Python's built-in `hash()` or the global `random`.
   - On success return the task's expected answer in a natural form (for numeric tasks include a short sentence sometimes, to exercise the grader). On failure choose a `failure_reason` (`wrong_answer`, `format_error`, `no_answer`, `tool_error`, `timeout`) with sensible weights and return a plausible wrong output.
   - Simulated latency and token counts from simple distributions. Do not sleep.
3. `runner.py`:
   - `run_suite(suite, agent, runs, seed, workers, existing=None, on_progress=None) -> RunResults`
   - Derive each run's seed deterministically from `(seed, task_id, run_index)`.
   - Use a `ThreadPoolExecutor` when `workers > 1`. Results must be identical regardless of worker count or completion order (sort before returning).
   - Catch every exception from `agent.run` and record a failed run with `failure_reason="exception"` and the error message. The suite must never crash because of one run.
   - Grade each output with the task's grader and record success and reason.
   - If `existing` results are provided, skip run indexes already present (this is the resume feature).
4. `io` helpers (put them in `models.py` or a small `storage.py`): write results JSON atomically (write to a temp file, then rename), load with validation, and generate a readable `run_id` such as `2026-10-26T14-30-00_demo-sim_sim`.

## Tests
- Determinism: same seed gives identical results; different seed differs.
- Order independence: `workers=1` and `workers=8` give identical results.
- Statistical sanity: a task with `p_success=0.7` over 2000 runs lands within 0.03 of 0.7.
- Crash safety: an agent that raises on every call yields all-failed runs and a completed suite.
- Resume: running with 5 existing runs per task and `runs=10` only executes the missing 5 and merges them.
- Round trip: write then load results equals the original.

## Done when
Tests and ruff pass. Commit, summarize, then wait for "next".
