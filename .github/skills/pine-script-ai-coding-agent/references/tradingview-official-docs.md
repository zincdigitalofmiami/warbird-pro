# TradingView Official Pine References

Use these pages as the primary technical authority for Pine Script behavior.

## Core docs

- First steps:
  - https://www.tradingview.com/pine-script-docs/primer/first-steps/
  - Use for Pine V6 onboarding, script types, and baseline authoring flow.
- Strategies:
  - https://www.tradingview.com/pine-script-docs/concepts/strategies/
  - Use for `strategy()` semantics, order simulation, Strategy Tester behavior, and backtest-oriented code.
- Visuals overview:
  - https://www.tradingview.com/pine-script-docs/visuals/overview/
  - Use for choosing between plot visuals and drawing visuals, and for script-wide visual settings in `indicator()` / `strategy()`.
- Debugging:
  - https://www.tradingview.com/pine-script-docs/writing/debugging/
  - Use for Pine-native debugging workflows. Prefer `log.*()` and chart outputs for interactive inspection.
- Profiling and optimization:
  - https://www.tradingview.com/pine-script-docs/writing/profiling-and-optimization/#optimization
  - Use for performance bottlenecks, Pine Profiler usage, and runtime optimization decisions.

## Practical guidance

- Prefer the official manual over generic recollection when syntax, execution model, visuals, or strategy behavior are in doubt.
- For strategy work, confirm behavior against the Strategies page before proposing order logic changes.
- For visual-heavy requests, check the Visuals overview before choosing plots, labels, lines, tables, or boxes.
- For bug hunts, use the Debugging page as the default reference surface.
- For speed or limit pressure, use the Profiling and optimization page before rewriting code.
