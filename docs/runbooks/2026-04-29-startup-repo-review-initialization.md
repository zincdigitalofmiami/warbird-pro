# Startup Repo Review Initialization Report

**Date:** 2026-04-29
**Status:** Permanent Initialization Record
**Mode:** Review first, then docs/memory persistence by user request

This report records the repo-state review that prompted the permanent
fresh-chat/start-of-day startup review rule. The initial review was read-only:
no files were modified, no builds/tests/training were run, and no Pine files
were touched during the review pass.

The follow-up implementation locked the review process into the repo authority
surfaces, the Codex handoff prompt, README, and durable memory.

## Current Architecture Snapshot

Warbird Pro is an indicator-only PineScript modeling workspace. Pine and
TradingView outputs are the active modeling truth. Optuna, AutoGluon, SHAP, and
local scripts are offline analysis tools that recommend Pine settings or build
changes after evidence review.

Active surfaces:

- `indicators/v7-warbird-institutional.pine` - live indicator surface
- `indicators/v7-warbird-strategy.pine` - Strategy Tester/export-compatible surface
- `indicators/v7-warbird-institutional-backtest-strategy.pine` - Optuna/backtest wrapper
- `scripts/optuna/` - local optimization workspace
- `scripts/ag/tv_auto_tune.py` and `scripts/ag/tune_strategy_params.py` - TradingView settings-trial helpers
- `docs/` plus `AGENTS.md`, `CLAUDE.md`, `README.md`, and `WARBIRD_MODEL_SPEC.md` - active authority stack

Legacy warehouse/FRED/macro `ag_training` paths are reference-only unless
explicitly reopened.

## Recent Direction Observed

Recent commits centered on:

- the indicator-only architecture reset
- Nexus footprint evidence enforcement
- 15m baseline and fib-core lock
- legacy v8 indicator removals
- 5m tuning preparation and phase contracts
- fib scanner guardrails after wide-fib regressions

The active direction is controlled 5m tuning while preserving the locked
backtest fib-core scope and promoting only evidence-backed settings/build
changes.

## Working Tree At Review Time

Branch state:

- current branch: `main`
- upstream: `origin/main`
- HEAD: `21aea81` (`Add fib scanner guardrails and sync Pine/backtest tuning surfaces`)
- divergence: aligned with `origin/main`

Existing WIP before this persistence change:

- modified: `docs/contracts/v7_interface_divergence.md`
- untracked:
  - `docs/runbooks/wb_strat_5m_simple_phaseA_preflight.md`
  - `docs/runbooks/wb_strat_5m_tv_capture_research.md`
  - `docs/runbooks/wb_strat_5m_verification_ledger.md`
  - `scripts/ag/run_phase_batch_via_tv_bridge.py`
  - `scripts/ag/tv_bridge_worker.mjs`

Stashes:

- `stash@{0}: On main: kirk-revert-strat-2026-04-28-fib-incident`
- `stash@{1}: On codex/nexus-visual-freeze-docs: epitaxy: pre-switch from codex/nexus-visual-freeze-docs`
- `stash@{2}: WIP on main: e047dbb Tighten pre-Phase-1 contract alignment`

Active branch/worktree signals:

- `codex/remove-backtest-fib-lock` exists and appears to loosen the current fib-core lock.
- `codex/wb-opt-bt-first-structural-fibs` is checked out in `/private/tmp/warbird-fib-revert-codex`.
- `feat/optuna-backtesting-setup` is ahead of its remote by two commits.

## Notable Issues And Inconsistencies Observed

- `docs/contracts/v7_interface_divergence.md` has an uncommitted change
  describing `Any Side Fib` / `Configured Anchor` behavior while the current
  backtest strategy source still says the execution contract uses only the
  configured anchor.
- Pine budget references are stale across some docs compared with current file
  headers.
- Exhaustion Z-score inputs remain in some strategy tuning-space JSON files
  even though active exhaustion logic removed Z-score use.
- `scripts/ag/tv_auto_tune.py` still contains 15m-oriented text while active
  5m runbooks are in flight.
- `scripts/optuna/runner.py` tags non-Nexus studies as `MES_15m`, which may be
  misleading for new 5m registry keys.
- `indicator_registry.json` still contains historical entries for retired or
  ignored Pine files.

These are observations only. This report did not resolve them.

## Stable Vs. In-Flux

Stable:

- local clone as source of truth
- indicator-only AG plan v6
- Pine/TradingView output as active training/modeling truth
- Nexus footprint-only evidence contract
- fib scanner guardrail banning the pivot-window `fibHtfSnapshot` variant
- protected backtest fib-core scope unless explicitly reopened

In flux:

- 5m strategy/backtest tuning process
- TradingView bridge/capture tooling
- backtest wrapper entry semantics
- tuning-space settings and stale docs around current Pine budgets
- old registry/documentation references to retired surfaces

## Permanent Initialization Change

The startup review rule is now locked into:

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `docs/INDEX.md`
- `docs/runbooks/README.md`
- `docs/agent-safety-gates.md`
- `.github/prompts/codex-handoff-review.prompt.md`
- `docs/runbooks/startup_repo_review.md`
- `MEMORY.md`
- `/Volumes/Satechi Hub/warbird-pro-state/claude-project-memory/project_startup_repo_review_initialization_2026-04-29.md`

Future fresh chats, start-of-day sessions, context resets, and resumed sessions
with unknown repo state must run `docs/runbooks/startup_repo_review.md` before
planning or implementation.
