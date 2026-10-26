# 04: Groq agent with rate-limit handling

**Read first:** PRD sections 6 (FR-10) and 10 (Groq agent).

## Task
1. `agents/tools.py`:
   - `calculator(expression: str) -> str` using a safe evaluator built on Python's `ast` module that allows only numbers and `+ - * / ** %` and parentheses. Never use `eval` or `exec`. Reject anything else with a clear error string.
   - `lookup_fact(key: str) -> str` over a small local dictionary of facts used by the demo suite.
   - OpenAI-format tool schemas for both.
2. `agents/groq_agent.py`:
   - Use the `openai` SDK with `base_url="https://api.groq.com/openai/v1"`. Read `GROQ_API_KEY` and `GROQ_MODEL` from the environment (load `.env` with python-dotenv). If either is missing, raise a friendly error telling the user to copy `.env.example`. Allow `--model` to override.
   - Tool-calling loop with a maximum of 6 steps. When the cap is hit, return `failure_reason="max_steps"`. Pass tool errors back to the model as tool messages.
   - Record `latency_ms`, token counts and `steps`.
   - A small `RateLimiter` for `--max-rpm` (default 20), thread-safe.
   - Backoff helper: on 429 and 5xx retry up to 6 attempts with exponential delay (base 1s, factor 2, max 30s) plus jitter. If a `Retry-After` header is present, wait at least that long. Put the delay calculation in a pure function so it can be unit tested without sleeping.
   - Never log or store the API key. `AgentOutput` and `config` must not contain it.
3. Add `suites/demo_groq.yaml`: 10 small tasks (some arithmetic needing the calculator, some `lookup_fact`, some formatting) with deterministic graders. Keep it small because free-tier limits are tight.
4. Wire the agent into `flake run --agent groq`. Default workers to 1 for Groq. `--resume` must work so a run interrupted by rate limits can be continued.
5. Add a short "Running with Groq" section to the README placeholder: how to get a key, set `.env`, choose a model from Groq's current model list, and the recommended command. Mention that free-tier limits apply and that results depend on the chosen model.

## Tests (no network)
- Use a fake client object that returns scripted responses.
- Tool loop: model calls the calculator, receives the result, then answers.
- Step cap returns `max_steps`.
- Backoff delays follow the expected schedule for attempts 1 to 5 with jitter disabled; `Retry-After` overrides when larger.
- Calculator rejects `__import__('os').system('x')`, attribute access and names.
- The API key never appears in serialized results.

## Done when
Tests pass without a key. Commit, summarize, and tell me exactly which command I should run myself with my own key. Then wait for "next".
