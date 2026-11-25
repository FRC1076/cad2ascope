# Kickoff prompt for Claude Code

Paste the text below into Claude Code from the root of the new `cad2ascope` repo, after unzipping this handoff into it (see README).

---

You're starting work on cad2ascope, a public tool for FRC Team 1076 that turns an Onshape robot assembly into an AdvantageScope robot model with moving mechanisms, plus generated Java for component poses and camera transforms.

Read `CLAUDE.md` first and follow it. Then read `docs/PLAN.md`, `docs/DECISIONS.md`, `private/TEAM-CONTEXT.md`, and `docs/PHASE0-CHECKLIST.md`.

Today's task is setup plus Phase 0 only:

0. Run `scripts/setup-mac.sh --check` and report the summary. Do not run `--store-keys`, `gh auth login`, or anything that asks for a password; those are Bill's. If any ACTION line remains, list them for Bill and wait. Never print the values of `ONSHAPE_ACCESS_KEY` or `ONSHAPE_SECRET_KEY`.
1. Set up the repo skeleton: `pyproject.toml` for Python 3.12 with uv, the `src/cad2ascope/` package with an empty CLI entry point, ruff and pytest config, the included BSD 3-Clause `LICENSE`, and a GitHub Actions workflow that runs lint and tests. Confirm `private/` is gitignored before the first commit.
2. Run `tests/fixtures/make_fixtures.py` and add a first test that loads every fixture's `expected.json`, so the oracle is in place.
3. Work through `docs/PHASE0-CHECKLIST.md`. Section B (AdvantageScope source) needs no credentials, so start there. For section A, check whether `ONSHAPE_ACCESS_KEY` and `ONSHAPE_SECRET_KEY` are set and whether Bill has shared the 2026 robot copy; if not, list exactly what you need from him and stop section A there.
4. Write `docs/phase0-findings.md` with the decision-gate summary at the top, and propose any changes to `docs/PLAN.md` in the same branch.

Then stop, open a pull request from `phase-0-spike`, and summarize for Bill: what you confirmed, what surprised you, what you need from him, and your recommendation on the export route. Do not start Phase 1.
