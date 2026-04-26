# Settings Artifact Contract

**Date:** 2026-04-26
**Status:** Active

## Purpose

The active output is a Pine settings/build artifact, not a server-side scoring
packet.

## Required Header Fields

- `artifact_version`
- `indicator_file`
- `indicator_commit`
- `symbol`
- `timeframe`
- `export_manifest_hash`
- `generated_at_utc`

## Required Body Fields

- champion Pine input settings
- rejected Pine input settings
- evaluated search space
- objective metrics
- IS/OOS or walk-forward metrics
- module keep/remove recommendations
- stop/target policy recommendation
- known failure modes
- recommended Pine changes, if any

## Rules

- The artifact must not include external feature gates.
- The artifact must not imply a live server-side scorer.
- Raw trial rows and raw SHAP matrices remain local artifacts only.
- Any Pine code or default-setting change still requires explicit approval.
