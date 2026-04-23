---
name: pine-script-ai-coding-agent
description: Use when a user wants to generate, debug, refactor, convert, or optimize TradingView Pine Script V6 indicators, strategies, screeners, alerts, or libraries through natural-language conversation. Mirrors a Pineify-style coding agent with compile-ready output, validation, self-correction, and iterative follow-up support.
---

# Pine Script AI Coding Agent

This skill is a Pineify-style workflow for Pine Script work: natural-language requests in, compile-ready Pine Script V6 out, with a validation loop before delivery.

## Canonical references

Load `references/tradingview-official-docs.md` when the task touches:

- first-time script structure or Pine V6 onboarding
- strategy behavior or backtest semantics
- visual/output design choices
- debugging techniques
- profiling and optimization

## Use when

- Building a new indicator, strategy, screener, alert surface, or Pine library
- Debugging Pine compiler errors, warnings, or bad runtime behavior
- Refactoring existing Pine code without changing intent
- Converting older Pine code to V6
- Optimizing Pine code for correctness, limits, or maintainability
- Acting like a conversational Pine coding assistant instead of a generic code generator

## Default contract

- Prefer Pine Script V6 unless the user explicitly asks for another version.
- Prefer full compile-ready output over fragmentary snippets.
- Prefer official namespaces, built-ins, and current syntax over manual reimplementation.
- If values are likely to be tuned, expose them as `input.*()` controls unless the user wants hardcoded constants.
- Be explicit about repaint policy, confirmation timing, and `request.security()` behavior when those matter.
- If the repo has its own Pine verification gates, run them in addition to this skill.

## Workflow

1. Classify the task: `build`, `debug`, `refactor`, `convert`, or `optimize`.
2. Lock the target contract:
   - script type: indicator, strategy, screener, alert helper, or library
   - overlay vs pane
   - required inputs, plots, alerts, and outputs
   - repaint and bar-close expectations
   - timeframe and `request.security()` constraints
3. If existing code is provided, patch that code instead of rewriting from scratch unless the user asks for a rewrite.
4. Draft Pine Script V6 code.
5. Run a validation loop before delivery:
   - If local Pine compiler or repo guards exist, run them.
   - If errors appear, fix them and revalidate.
   - If no compiler is available, do a static Pine V6 sanity pass and say what remains unverified.
6. Return:
   - the full code or exact patch
   - a short summary of what changed
   - validation status
   - the next useful follow-up prompts when iteration is likely

## Built-in behaviors

### Code generation

- Translate plain-language requirements into Pine V6.
- Build configurable inputs, plots, alerts, and strategy settings when requested.
- Support indicators, strategies, screeners, alerts, and libraries.

### Debugging

- Treat compiler errors and warnings as first-class inputs.
- Fix namespace drift, deprecated functions, series/type mismatches, scope issues, `request.security()` misuse, repaint mistakes, and TradingView output-budget pressure before stopping.
- Prefer the smallest safe fix over a wholesale rewrite.

### Refactoring and optimization

- Preserve behavior unless the user asks for semantic changes.
- Make performance-aware changes only when justified: fewer duplicated calculations, safer state, lower `request.*` pressure, fewer plots, clearer confirmation logic.
- Do not “clean up” unrelated logic.

### Preference-aware iteration

If the user states durable Pine preferences, apply them consistently, for example:

- “Always use Pine Script V6”
- “Expose all configurable values as inputs”
- “Prefer `ta.sma()` over manual averaging”
- “Keep alerts structured and explicit”

State when those preferences materially changed the generated code shape.

## Prompting tips

- Strong prompts name the script type, logic, inputs, plots, alerts, and repaint expectations.
- Existing code is high-value context; use it whenever the user already has a draft.
- Follow-up turns should refine, not restart: add inputs, alerts, MTF filters, visuals, optimizations, or bug fixes incrementally.

## When not to use

- Pure TradingView UI operations with no Pine code work
- Repo-specific schema, data, or ML contract work where Pine is incidental
- Tasks where another domain skill is primary and Pine is only a minor output surface

## Source

This skill is modeled on the workflow described in Pineify’s Pine Script AI Coding Agent manual:

- https://pineify.app/manual/features/pine-script-ai-coding-agent/

Primary technical authority for Pine behavior should come from the official TradingView manual referenced in `references/tradingview-official-docs.md`.
