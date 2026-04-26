# Nexus Visual And Plot Freeze

**Date:** 2026-04-26
**Status:** Active hard contract
**Indicator:** `indicators/warbird-nexus-machine-learning-rsi-optuna-fast-test.pine`

## Purpose

This contract freezes the Nexus ML RSI styling and visible-output surface.
Future tuning, optimization, repair, or contract work must not treat Nexus
visuals as an available edit surface.

## Frozen Surfaces

Agents must not remove, rename, hide, consolidate, recolor, restyle, or
otherwise change any of these Nexus surfaces unless Kirk explicitly requests
that exact visual/plot edit in the current session:

- Warbird color constants and color inputs
- theme text colors and dashboard color choices
- oscillator line color behavior
- price-bar coloring through `barcolor`
- watermark text, placement, colors, and default visibility
- dashboard table and KNN table presentation
- visible `plot`, `plotshape`, `fill`, `hline`, label, and line styling
- visible output count and plot inventory
- divergence, cross-dot, fatigue, confluence, zone, regime, and volume-flow
  rendering

## Approved Visual Baseline

The approved Nexus visual baseline includes:

- Warbird teal `#26C6DA`
- Warbird red `#cc0000`
- Warbird yellow `#FFEB3B`
- neutral gray `#888888`
- `WARBIRD PRO` watermark
- current adaptive oscillator coloring
- current `barcolor(lineCol, title = "Nexus Oscillator Bar Color")`
- current dashboard, KNN panel, plots, fills, cross dots, fatigue markers, and
  divergence markers

## Allowed Nexus Work

Allowed Nexus work is limited to:

- numeric input default changes approved for tuning
- nonvisual calculation fixes approved for the current task
- Optuna/profile changes that use the approved TradingView/Pine
  `request.footprint()` `nexus_fp_*` evidence contract
- documentation updates that preserve this visual freeze

Numeric settings approval does not authorize visual, styling, or visible-output
edits.

## Required Stop Trigger

Stop before editing Nexus if the change touches any of these strings or nearby
logic:

- `WARBIRD_BULL`
- `WARBIRD_BEAR`
- `WARBIRD_YELLOW`
- `showWatermarkInput`
- `WM_COLOR`
- `barcolor`
- `plot(`
- `plotshape(`
- `fill(`
- `table.cell`
- `knnTable`
- `dashTable`

If the requested work is not explicitly about that exact visual/plot item, leave
it untouched and report that the Nexus visual/plot freeze applies.
