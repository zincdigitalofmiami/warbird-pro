# Stop And Target Policy Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

Defines stop/target policy handling for indicator-only modeling.

## Rule

Stops and targets are Pine settings or Pine state-machine outputs. The active
modeling program may rank settings and policies, but it may not introduce a
server-side stop family that Pine does not implement.

## Requirements

- Stop/target assumptions must be recorded in the export manifest.
- Strategy Tester commission, slippage, Bar Magnifier, and fill settings must be
  recorded.
- Any new stop/target policy requires Pine approval and Pine verification.
- Emergency/structural stop rules in Pine remain operator-safety logic and must
  be reflected in reported backtests when active.
