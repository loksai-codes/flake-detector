# 05: CI, README and polish

**Read first:** PRD sections 12, 13 and 14.

## Task
1. `.github/workflows/ci.yml`: on push and pull request, Python 3.11 and 3.12, install the package with dev extras, run `ruff check .` and `pytest`. No secrets required.
2. Coverage check: run `pytest --cov` locally, list uncovered branches in `metrics.py`, `runner.py`, `compare.py` and `groq_agent.py`, and add tests for them. Do not chase 100% on trivial code.
3. Write the final `README.md`. Structure:
   - Logo (`assets/logo.svg`, I will add the file) with the project name and a one-line pitch
   - "Why": the single-run problem, in 3 to 4 sentences
   - Quickstart: install, run the simulated demo, view the report (copy-paste commands that really work)
   - What you get: embed `examples/charts/pass_curves.png` and a trimmed excerpt of the sample report, clearly labeled **simulated data**
   - How `pass@k` and `pass^k` differ, with one small worked example
   - Run it on a real agent with Groq (short, links to the section you wrote earlier)
   - CI usage: show `flake compare --fail-on-regression` inside a GitHub Actions step
   - Project structure, design choices, limitations (small samples, deterministic graders only)
   - A section titled "Results with Groq" containing a clearly marked TODO table for me to fill in after I run it. **Do not invent numbers.**
   - License and contact placeholders
4. Final check against the PRD acceptance criteria. Produce a checklist with pass or fail for each item and the command you used to verify it.
5. Run a secrets scan by hand: search the repo and git history for `gsk_`, `GROQ_API_KEY=` with a value, and `.env` files. Report the result.

## Done when
CI workflow is valid, all acceptance criteria pass, README renders cleanly, and the secrets scan is clean. Commit with `docs: final README and CI`, summarize, and list anything I must do manually (add logo, set repo description and topics, run the Groq demo and fill in the results table).
