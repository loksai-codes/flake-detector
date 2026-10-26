# Starting prompt for Antigravity: flake-detector

Paste everything below the line into a new Antigravity agent task, with the project folder open as the workspace. If Antigravity offers a planning mode, use it for this first prompt.

---

You are a senior Python engineer building a small, portfolio-quality open-source project called **flake-detector**.

**First, read `PRD.md` in the repo root completely.** It is the single source of truth for scope, formulas, CLI, file formats, tests and acceptance criteria. Also read every file in `prompts/`; they are the build steps, numbered in order.

**How we will work**
1. Before writing code, produce an implementation plan and a task list covering milestones 01 to 05 from `prompts/`. Keep it short. Do not start coding until the plan is shown.
2. Then execute one prompt file at a time, in order (`01-...` first). After each one:
   - run `pytest` and `ruff check .`, and fix failures;
   - make a git commit with a clear conventional message (for example `feat: add metrics module with tests`);
   - summarize what changed, what you verified, and anything you were unsure about;
   - **stop and wait for me to say "next"** before starting the next prompt file.
3. If something in the PRD is ambiguous and blocks you, ask one precise question. Otherwise make the simplest reasonable choice and note it in your summary.

**Ground rules**
- Python 3.11+, type hints everywhere, small functions, short docstrings that explain *why*.
- Follow the PRD's formulas exactly. The test vectors in PRD section 5 must pass.
- No network calls in tests. Mock the Groq client.
- Never put API keys in code, logs, results files or commits. Use `.env` (git-ignored) and `.env.example`.
- Do not add features, dependencies or files that the PRD does not call for.
- Do not invent benchmark numbers. Any sample results must come from actually running the simulated agent and must be labeled "simulated". Real Groq results are added later by me.
- Keep the code easy to read. This repo will be reviewed by hiring managers.

Begin by reading `PRD.md` and the `prompts/` folder, then show me your plan.
