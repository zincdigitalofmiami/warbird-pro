# GitHub Copilot Chat — Instruction Surface

**This file defers to [AGENTS.md](../AGENTS.md) as the authoritative workspace instruction surface. It exists only to ensure Copilot Chat loads the same context every other AI tool in this workspace loads.**

## Read order

1. Open [`AGENTS.md`](../AGENTS.md) at repo root — this is the primary instruction file. Every rule, read order, plan reference, and verification gate lives there.
2. Follow the "Read Order" section in AGENTS.md (docs index, master plan, contracts, runbooks, CLAUDE.md, etc.).
3. For TRAINING work (AutoGluon, Monte Carlo, SHAP, indicator optimization, pre-training audits), consult the Training Skills Registry at the bottom of AGENTS.md, then open the relevant `SKILL.md` file:
   - `.github/skills/<skill-name>/SKILL.md` ← Copilot-native location
   - `.claude/skills/<skill-name>/SKILL.md` ← identical copy
   - `.kilocode/skills/<skill-name>/SKILL.md` ← identical copy

## Training skills available in this workspace

Eleven skills, mirrored across the three locations above. Full descriptions in each `SKILL.md`:

- `training-pre-audit` — pre-launch checklist
- `training-gbm-only` — fast GBM iteration
- `training-full-zoo` — multi-family AutoGluon runs
- `training-shap` — feature importance + leakage audit
- `training-monte-carlo` — P&L analysis on completed predictors
- `training-quant-trading` — time-series discipline
- `training-ag-best-practices` — AutoGluon 1.5 config gotchas
- `training-ag-feature-finder` — unused AG 1.5 capabilities
- `training-supabase-data` — training read patterns for local `warbird` PG17
- `training-tv-backtesting` — TradingView strategy-tester workflow
- `training-indicator-optimization` — sweep indicator parameters

## Hard rules that override any default Copilot behavior

These come from AGENTS.md and CLAUDE.md — they are non-negotiable regardless of what Copilot's base training suggests:

1. **Never push to remote or deploy without explicit user approval each time.** Prior approvals do not carry forward.
2. **Never use mock data.** Real data or nothing.
3. **Never use an ORM (including Prisma).** Direct SQL via `psycopg2` only.
4. **Never add `.github/copilot-instructions.md` that competes with `AGENTS.md`.** This file is a redirector, not a competing surface. Do not expand it into authoritative content.
5. **Pine indicator changes require all five verification gates** (pine-facade compile, pine-lint, check-contamination, strategy-parity, npm build) before commit. See AGENTS.md.
6. **Local warehouse migrations** live in `local_warehouse/migrations/` with the `local_schema_migrations` ledger — NOT `supabase/migrations/`.
7. **Time-series discipline is absolute.** No random shuffle, minimum 1-session embargo, AutoGluon `--num-bag-folds 0` mandatory for time-series. See `training-quant-trading`.
8. **`.remember/` files are append-only.** Never overwrite.

## When Copilot Chat is asked to suggest code

- Read the relevant SKILL.md first if the task touches training, indicators, or the warehouse
- Verify the trainer's `hyperparameters` dict before claiming a run is "full zoo" — a dict containing only GBM silently locks out every other model family
- Check migration 014 and 017 constraints match the trainer's `metric_scope` / `run_kind` spelling before proposing any DB lineage changes
- MES commission model: **flat 1 tick per trade ($1.25)** — NinjaTrader Basic free account. Do not suggest round-trip doubling, slippage adders, or broker-tier commission tables unless explicitly asked

## What NOT to put in this file

- Detailed instructions (those belong in AGENTS.md)
- Active plan wording (that lives in `docs/MASTER_PLAN.md` and changes during testing)
- Skill bodies (those live in `.github/skills/<name>/SKILL.md` and their mirrors)

Keep this file thin. Its only job is to redirect Copilot Chat to the authoritative surface so Copilot loads the same context Claude Code / Kilocode / Codex already load.
