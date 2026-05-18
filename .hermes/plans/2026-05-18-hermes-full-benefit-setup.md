# Hermes Full-Benefit Setup Plan

**Status:** Implemented in phases from the 2026-05-18 locked operator decision set.

## Locked Decisions

- Hermes policy lives under `.hermes/rules/`.
- No Hermes policy, plan, or validator authority is stored under another agent
  surface.
- Primary Hermes path is OpenAI Codex OAuth: `openai-codex / gpt-5.5` for
  planning and Codex execution for implementation.
- OpenRouter remains available for explicit fallback/use, not active primary.
- `computer_use` stays disabled.
- Enabled Hermes toolsets for this setup: `web`, `browser`, `image_gen`,
  `cronjob` plus the existing safe daily toolsets.
- Web/search uses fetch MCP only; no extra search-provider account signup.
- MCP order: filesystem, GitHub, Supabase read-only, fetch, Warbird status.
- Gateway is on-demand only. Launchd triggers bounded cron ticks and EOD cleanup
  without keeping gateway hot all day.
- Memory/skill improvement means daily reflection into memory entries and skill
  drafts; no automatic skill promotion.
- VS Code click target is a local `warbird-hermes` extension that opens ACP.

## Out Of Scope

- Pine edits.
- Training, SHAP, Monte Carlo, or dataset builds.
- TradingView automation.
- Supabase mutations.
- Committing pre-existing Pine/trainer/test WIP without the full required gates.
