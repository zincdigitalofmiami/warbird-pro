# Packet Schema Contract

**Status:** Active

## Purpose

Defines the offline packet artifact produced from local training and published to cloud serving surfaces.

## Required Header Fields

- `packet_version`
- `feature_schema_version`
- `trained_on_utc`
- `repo_commit`
- `dataset_manifest_hash`
- `label_contract_version`

## Required Body Fields

- ordered `feature_list`
- model output specification
- calibration metadata
- admitted `stop_family_id` set
- packet checksum

## Ordered Feature Rule

- every packet must include an explicit ordered `feature_list`
- the ordered list must contain Tier 1 features only
- packet consumers must reject packets whose `feature_schema_version` or `feature_list` does not match the active runtime contract

## Output Rule

Packets may publish:

- calibrated TP1 probability
- calibrated TP2 probability
- calibrated reversal or failure probability
- bounded stop-family recommendation or ranking

Packets may not publish:

- arbitrary free-form stop prices
- raw research-only features
- Tier 2-only diagnostics

## Compatibility Rule

- unknown schema versions are rejected
- missing required header fields are rejected
- extra feature names not allowed by the active feature catalog are rejected
