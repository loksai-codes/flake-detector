# PRD: flake-detector

**Status:** Ready to build · **Target:** one working day · **License:** MIT

## 1. Summary

`flake-detector` is a Python CLI and library that runs an AI agent on a task suite many times and reports how *consistent* it is, not just how accurate it is. It outputs per-task and suite-level success rates with confidence intervals, `pass@k` vs `pass^k`, a flakiness ranking, charts, and a regression check between two runs that can fail a CI build.

## 2. Problem

Agent evaluations usually report a single run: "the agent passed 8 of 10 tasks." Because LLM agents are non-deterministic, that number hides two things: how much it would change on a rerun, and whether the agent is dependable on any given task. A task that passes once and fails twice looks like a pass. Teams ship agents that "worked in the demo" and fail in production.

## 3. Goals and non-goals

**Goals**
- G1. Run any agent N times per task and compute correct consistency statistics.
- G2. Make the gap between "can succeed" (`pass@k`) and "always succeeds" (`pass^k`) visible in one chart.
- G3. Provide a `compare` command that detects real regressions between two runs and can gate CI.
- G4. Work with no API key (simulated agent) and with a real LLM agent via Groq's OpenAI-compatible API.
- G5. Be small, typed, tested and readable, because it is a portfolio piece.

**Non-goals**
- Not a general LLM benchmark or leaderboard.
- No web UI, database or hosted service.
- No LLM-as-judge in v1 (only deterministic graders).
- No support for distributed or multi-machine runs.

## 4. Users and use cases

- *Agent builder:* "I changed my prompt. Is the agent actually better or just luckier?"
- *Reviewer / hiring manager:* reads the README and the sample report to judge the author's grasp of evaluation.
- *CI pipeline:* runs `flake compare --fail-on-regression` on every prompt change.

## 5. Concepts and formulas

For one task with `n` runs and `c` successes:

- **Success rate:** `p = c / n`
- **Wilson 95% interval** (z = 1.96):
  `center = (p + z²/(2n)) / (1 + z²/n)`
  `half = z * sqrt(p(1-p)/n + z²/(4n²)) / (1 + z²/n)`
  interval = `[center - half, center + half]`, clipped to [0, 1]
- **pass@k** (probability at least one of k sampled runs succeeds): `1 - C(n-c, k) / C(n, k)`; equals 1 if `n - c < k`
- **pass^k** (probability all k sampled runs succeed): `C(c, k) / C(n, k)`; equals 0 if `c < k`
- **Flakiness score:** `4 * p * (1 - p)` (0 for always-pass or always-fail, 1 at 50%)
- **Task status:** `consistent` if `c == n`; `failing` if `c == 0`; otherwise `flaky`

Suite level: mean `pass@1`, mean `pass^k`, percentage of consistent / flaky / failing tasks, and the curve of mean `pass@k` and `pass^k` for `k = 1..K`.

**Test vectors (must pass, tolerance 1e-3):**

| n | c | k | Expected |
|---|---|---|---|
| 10 | 7 | n/a | Wilson interval [0.397, 0.892] |
| 5 | 5 | n/a | Wilson interval [0.5655, 1.0] |
| 10 | 3 | 1 | pass@1 = 0.3, pass^1 = 0.3 |
| 10 | 3 | 2 | pass@2 = 0.5333, pass^2 = 0.0667 |
| 10 | 3 | 5 | pass@5 = 0.9167, pass^5 = 0 |
| 10 | 10 | 5 | pass@5 = 1, pass^5 = 1 |
| 10 | 0 | 5 | pass@5 = 0, pass^5 = 0 |

## 6. Functional requirements

- **FR-1 Suite loading (MUST).** Load a YAML suite (format in section 7). Validate with Pydantic; clear error messages with file and task id.
- **FR-2 Graders (MUST).** Deterministic graders: `exact` (options: `case_sensitive`, `strip`), `contains`, `regex`, `numeric` (`abs_tol`, `rel_tol`). A grader returns `success` and a `failure_reason` from: `wrong_answer`, `format_error`, `no_answer`, `tool_error`, `timeout`, `exception`, `max_steps`.
- **FR-3 Agent interface (MUST).** An agent is any object with `run(task, seed) -> AgentOutput` where `AgentOutput` has `answer`, optional `error`, `latency_ms`, `tokens_in`, `tokens_out`, `steps`.
- **FR-4 Runner (MUST).** Run every task `runs` times. Seeds are derived deterministically from `(base_seed, task_id, run_index)` so results do not depend on execution order. Support a worker count. An exception in one run is recorded as a failed run and never stops the suite.
- **FR-5 Results file (MUST).** Write one JSON file per run (schema in section 7). Never store API keys.
- **FR-6 Resume (SHOULD).** `--resume` skips run indexes already present in the results file, so a rate-limited run can be continued.
- **FR-7 Report (MUST).** Generate a Markdown report and PNG charts from a results file (section 9).
- **FR-8 Compare (MUST).** Compare two results files (section 8). With `--fail-on-regression`, exit code 1 on a significant regression.
- **FR-9 Simulated agent (MUST).** Deterministic, no network, with per-task success probabilities from the suite file.
- **FR-10 Groq agent (MUST).** A tool-using agent over Groq's OpenAI-compatible API, with rate-limit handling (section 10).
- **FR-11 CLI (MUST).** `flake run | report | compare` (section 8).

## 7. Data formats

**Suite YAML**

```yaml
name: demo-sim
description: Small mixed suite for demonstrating flakiness
tasks:
  - id: arith-01
    category: math
    prompt: "What is 17 * 23? Answer with just the number."
    grader: { type: numeric, expected: 391, abs_tol: 0 }
    sim: { p_success: 0.95 }          # used only by the simulated agent
  - id: format-01
    category: formatting
    prompt: "Return the word 'blue' in uppercase."
    grader: { type: exact, expected: "BLUE", case_sensitive: true }
    sim: { p_success: 0.6 }
```

**Results JSON (top level keys)**
`schema_version`, `run_id`, `created_at`, `agent` (`name`, `model`, `config`), `suite` (`name`, `sha256_12`), `params` (`runs`, `k`, `seed`), `tasks[]`, each with `id`, `category`, and `runs[]` containing `index`, `success`, `failure_reason`, `answer`, `error`, `latency_ms`, `tokens_in`, `tokens_out`, `steps`.

## 8. CLI specification

```
flake run --suite PATH --agent sim|groq --runs 20 --k 5 --seed 42 \
          [--workers 8] [--out results/] [--resume] [--max-rpm 20] [--model NAME]
flake report RESULTS.json [--out report.md] [--charts-dir charts/]
flake compare A.json B.json [--alpha 0.05] [--fail-on-regression]
```

- Exit codes: `0` success, `1` regression detected (only with the flag), `2` usage or config error.
- Validation: `1 <= k <= runs`.
- **Compare method:** per task, flag a *significant change* when the two Wilson intervals do not overlap. At suite level, run a paired bootstrap over tasks (1000 resamples, fixed seed) on the difference in mean success rate; report the 95% percentile interval. A **regression** is a suite-level interval whose upper bound is below 0.

## 9. Reports

Markdown report sections, in order:
1. Run metadata (agent, model, suite, hash, runs, k, seed, date)
2. Suite summary (mean `pass@1`, mean `pass^k`, % consistent / flaky / failing, mean latency, total tokens)
3. Per-task table sorted by flakiness descending: task, category, n, successes, rate, 95% CI, `pass@k`, `pass^k`, status
4. Failure reasons breakdown (counts by `failure_reason`)
5. Charts (below), embedded by relative path

Charts (Matplotlib, headless backend, clean readable style, colorblind-safe, file names stable):
- `pass_curves.png`: mean `pass@k` and `pass^k` for `k = 1..K`; the widening gap is the main visual.
- `task_rates.png`: per-task success rate with Wilson error bars, sorted by rate.

## 10. Agents

**Simulated agent**
- Success probability per task from `sim.p_success` (default 0.8).
- Randomness from a `random.Random` seeded with a stable hash of `(seed, task_id, run_index)`; never use global state or Python's salted `hash()`.
- On failure, choose a `failure_reason` and produce a plausible wrong output.
- Latency drawn from a log-normal distribution (simulated, no sleeping).

**Groq agent**
- Use the `openai` Python SDK with `base_url="https://api.groq.com/openai/v1"`. Read `GROQ_API_KEY` and `GROQ_MODEL` from the environment (`.env` supported). Never hardcode a model name as the only option, because Groq's model catalog changes.
- Tool-calling loop, max 6 steps, temperature configurable (default 0.7 so variance is visible).
- Two local tools: `calculator(expression)` (safe AST-based evaluation, no `eval`) and `lookup_fact(key)` (small local dictionary).
- Retry on HTTP 429 and 5xx with exponential backoff and jitter; honor the `Retry-After` header when present; stop after 6 attempts and record `exception`.
- `--max-rpm` throttles request rate; default 20.
- Free-tier limits are tight, so the demo suite must be small (about 10 tasks x 10 runs).

## 11. Architecture and repo layout

```
flake-detector/
  README.md  PRD.md  LICENSE  pyproject.toml  .gitignore  .env.example
  src/flake_detector/
    __init__.py  models.py  metrics.py  grading.py  suite.py
    runner.py  report.py  compare.py  cli.py
    agents/  base.py  simulated.py  groq_agent.py  tools.py
  suites/    demo_sim.yaml  demo_groq.yaml
  tests/     test_metrics.py  test_grading.py  test_suite.py  test_runner.py
             test_simulated.py  test_compare.py  test_groq_agent.py  test_cli.py
  examples/  sample_results.json  sample_report.md  charts/
  prompts/   (the build prompts)
  assets/    logo.svg
  .github/workflows/ci.yml
```

Stack: Python 3.11+, Pydantic v2, Typer, Rich, PyYAML, Matplotlib, openai SDK, python-dotenv, pytest, ruff.

## 12. Non-functional requirements

- Fully deterministic given the same suite, agent and seed (simulated agent).
- Simulated demo (12 tasks x 20 runs) completes in under 5 seconds.
- Type hints throughout; `ruff` clean; no network access in tests (mock the Groq client).
- No secrets in the repo, logs or results files; `.env` git-ignored.

## 13. Testing strategy

- Unit tests for every formula using the test vectors in section 5.
- Property checks: `0 <= pass^k <= pass@k <= 1`; Wilson interval always contains `p`.
- Determinism test: two simulated runs with the same seed produce identical results; different seeds differ.
- Runner test: an agent that raises on every run does not crash the suite.
- Groq agent tests with a fake client: tool loop, 429 backoff schedule, `Retry-After` handling, step cap.
- CLI tests with Typer's `CliRunner`, including exit codes for `compare`.

## 14. Acceptance criteria

1. `pip install -e .` then `flake run --suite suites/demo_sim.yaml --agent sim --runs 20 --k 5 --seed 42` works with no key.
2. `flake report` produces the Markdown report and both charts.
3. `pass@k` and `pass^k` values match every test vector.
4. `flake compare` exits 1 on a deliberately degraded simulated run and 0 on identical runs.
5. `pytest` and `ruff check` pass; CI is green.
6. README includes a real sample report and charts from the simulated agent, clearly labeled "simulated". Groq results are added only after the owner runs them with their own key.

## 15. Milestones (one day)

| Block | Work |
|---|---|
| 1 hr | Scaffold, models, metrics, graders, suite loader, tests |
| 1 hr | Runner, simulated agent, results I/O, determinism tests |
| 1 hr | CLI, report, charts, compare |
| 1 hr | Groq adapter, rate-limit handling, mocked tests |
| 30 min | CI, README, sample outputs, polish |

## 16. Risks

- Free-tier rate limits slow real runs. *Mitigation:* small suite, `--max-rpm`, `--resume`.
- Small suites give wide intervals. *Mitigation:* the report states this and shows the intervals instead of hiding them.
- Model names change. *Mitigation:* model comes from config or environment.
