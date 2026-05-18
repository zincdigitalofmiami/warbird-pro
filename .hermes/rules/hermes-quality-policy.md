# Warbird Hermes Quality Policy

**Status:** Active Hermes authority for Warbird
**Scope:** Hermes config, hooks, skills, MCPs, gateway/cron, memory, ACP, and local Hermes tooling

Hermes is its own Warbird execution layer. `AGENTS.md` remains the repo
instruction authority; this file defines only the Hermes execution contract
beneath it.

## Primary Model Lane

- Primary planning model path: `openai-codex / gpt-5.5`.
- Primary execution path: OpenAI Codex OAuth through Hermes Codex Responses mode.
- Config values:
  - `provider: openai-codex`
  - `model: gpt-5.5`
  - `api_mode: codex_responses`
  - `base_url: https://chatgpt.com/backend-api/codex`
- OpenRouter remains available for all work as an explicit fallback/provider
  path, not the active primary path.
- Current fallback order: `openrouter / moonshotai/kimi-k2.6`, then
  `openrouter / deepseek/deepseek-r1`.
- Do not describe fallback success as primary-model readiness.

Primary-readiness smoke tests:

```bash
hermes chat -Q --provider openai-codex -m gpt-5.5 --ignore-rules \
  -q 'Reply exactly: OPENAI_CODEX_CONNECTED'
hermes chat -Q --provider openai-codex -m gpt-5.5 -t file,terminal --ignore-rules \
  -q 'Reply exactly: OPENAI_CODEX_TOOLS_CONNECTED. Do not call any tools.'
```

## Hermes Baseline Requirements

1. Keep secrets in `~/.hermes/.env` only. Never commit tokens or service keys.
2. Keep `approvals.mode` fail-closed (`manual` or stricter).
3. Keep `hooks_auto_accept: false`.
4. Keep high-risk toolsets disabled unless explicitly approved for a task.
5. `computer_use` stays disabled for Warbird by default because terminal,
   browser, file tools, and filesystem MCP cover host access without the
   TradingView automation risk.
6. Gateway is on-demand only. Do not run gateway as an always-on memory burner.
7. Scheduled Warbird cleanup/reflection is launchd-driven and bounded; it must
   stop gateway after the scheduled work completes.
8. No Hermes skill may override `AGENTS.md`, `CLAUDE.md`, or active contract docs.
9. Self-improvement means memory curation and skill drafts. It is not model
   weight training or autonomous promotion of unreviewed skills.

## Enabled Warbird Tool Profile

Safe daily work keeps these enabled:

- `terminal`
- `file`
- `code_execution`
- `skills`
- `todo`
- `memory`
- `session_search`
- `clarify`

Approved for this Hermes setup work:

- `web` using fetch-only/no-signup tooling where possible
- `browser` using local browser automation
- `image_gen` through the configured OpenAI/Codex image path
- `cronjob` for bounded scheduled jobs

Still disabled by default:

- `computer_use`
- `delegation`
- `messaging`
- `vision`
- `tts`
- `video`
- `video_gen`
- `homeassistant`
- `spotify`
- `yuanbao`
- `moa`

## MCP Policy

Configured MCPs must be added one at a time and tested before use:

1. filesystem MCP rooted at `/Users/zincdigital` and `/Volumes/Satechi Hub`
2. GitHub MCP using `GITHUB_TOKEN` from `~/.hermes/.env`
3. Supabase MCP scoped to the Warbird project and read-only by default
4. fetch MCP for account-free URL retrieval
5. custom Warbird status MCP under `.hermes/mcp/warbird-status/`

Do not enable mutating Supabase MCP tools by default. Cloud Supabase remains
runtime/support only and must not receive raw training data, labels, or full
research artifacts.

## ACP Policy

- `hermes acp --check` proves CLI-side ACP readiness only.
- VS Code end-to-end ACP readiness requires the ACP Client panel to connect to
  `Hermes Agent` and return exactly `VSCODE_ACP_READY`.
- The local `warbird-hermes` VS Code extension exists only as a click target for
  Hermes ACP. It must not bypass ACP permissions or Hermes approval settings.

## Required Hermes Validation

For Hermes config, hook, skill, MCP, gateway, ACP, or integration work, run:

```bash
git status --short
hermes config check
hermes doctor
hermes memory status
hermes lsp status
hermes hooks doctor
tc_validator --fast
```

If the work claims primary-model readiness, also run the OpenAI Codex smoke
tests above and confirm exact responses without fallback.

If the work claims VS Code ACP readiness, verify the ACP Client panel returns
`VSCODE_ACP_READY`.

This policy does not define or require validation for any non-Hermes agent
surface.

## Hard Rules

- No secret material in repo files.
- No silent enablement of gateway, messaging, delegation, or computer-use lanes.
- No package-install commands without explicit approval in the current session.
- No claim of validation pass without command evidence.
- No quality-playbook runtime resurrection.
- No TradingView recovery automation through Hermes.
