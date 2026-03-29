# Point-In-Time Quant ML Reference Guide

Use this reference to keep ML audits grounded in published guidance about leakage, preprocessing discipline, and time-series feature alignment.

## Sources Used

- scikit-learn common pitfalls: https://scikit-learn.org/stable/common_pitfalls.html
- Look-ahead bias in rolling-window features: https://www.mhtechin.com/support/look-ahead-bias-in-rolling-window-features/

## scikit-learn Guidance To Enforce

- Split train and test before any fitted preprocessing.
- Never call `fit` or `fit_transform` on data that includes evaluation samples.
- Pipelines are the preferred way to keep preprocessing and model fitting aligned between train, validation, and inference.
- Reproducibility depends on explicit randomness control; uncontrolled or mutated randomness can make results hard to compare across runs.

## Time-Series And Quant Guidance To Enforce

- Rolling and expanding features must be aligned to the forecast origin, usually by shifting them by at least one period or by the forecast horizon.
- Global scalers fitted across the full dataset leak future information into the past.
- Exogenous data such as macro releases, news, and revisions must respect publication lag and availability at the decision timestamp.
- Walk-forward or rolling-origin validation is the safer default for financial time-series work.

## What To Flag Immediately

- Any feature built with future bars or same-bar outcomes hidden inside the predictor.
- Any training row whose features cannot be reconstructed from data available at the decision timestamp.
- Any dataset generation logic that uses wall-clock runtime, current date, or mutable external state to define historical features or sample weights.
- Any mismatch between training features and live inference inputs.
- Any predicted-price framing that conflicts with an explicitly outcome-state decision contract.

## Warbird-Specific Implications

- The bar-close timestamp and timezone are contract-critical. If they drift, the dataset is not trustworthy.
- Continuous or rolled futures series need explicit handling; do not assume correlation or return features are point-in-time safe without checking symbol activity and timing.
- Materialized views and derived news surfaces are only safe if their refresh semantics match the historical decision timestamp.
