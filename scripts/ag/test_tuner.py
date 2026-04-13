"""
test_tuner.py — Offline tests for the Warbird v7 strategy tuner.

Tests score_trial (Phase B), failure classification (Phase C), input validation,
trial record building, and structural invariants. No live TV or Postgres required —
psycopg2 is mocked at import time.

Run:  python3 -m pytest scripts/ag/test_tuner.py -v
"""
from __future__ import annotations

import json
import math
import sys
import unittest.mock as mock
from pathlib import Path

# Mock psycopg2 before importing tuner modules (no live DB needed).
sys.modules["psycopg2"] = mock.MagicMock()
sys.modules["psycopg2.extras"] = mock.MagicMock()
sys.path.insert(0, str(Path(__file__).parent))

import tune_strategy_params as tsp
import tv_auto_tune as tva


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _balanced_metrics(
    total: int = 1000,
    win_rate: float = 0.55,
    pf: float = 1.5,
    net: float = 5000.0,
    dd_pct: float = 8.0,
    years: int = 6,
) -> dict:
    """Build a plausible metrics dict for scoring tests."""
    wins = int(total * win_rate)
    losses = total - wins
    long_trades = total // 2
    short_trades = total - long_trades
    by_year = {str(2020 + i): round(net / years, 2) for i in range(years)}
    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "percent_profitable": round(wins / total * 100, 2),
        "gross_profit": round(net * pf / (pf - 1), 2) if pf != 1 else net,
        "gross_loss": round(net / (pf - 1), 2) if pf != 1 else 0,
        "net_pnl": net,
        "profit_factor": pf,
        "max_drawdown": round(dd_pct * 100, 2),
        "max_drawdown_pct": dd_pct,
        "return_on_initial_pct": round(net / 10000 * 100, 2),
        "survival_30_tick_pct": 75.0,
        "long": {"trades": long_trades, "profit_factor": pf},
        "short": {"trades": short_trades, "profit_factor": pf},
        "by_year": by_year,
        "footprint_cohort": {
            "from_date": "2025-01-01",
            "trades": 200,
            "net_pnl": 1000.0,
            "profit_factor": 1.3,
            "long_trades": 100,
            "short_trades": 100,
        },
    }


def _default_objective() -> dict:
    """Load objective block from the actual tuning space JSON."""
    space_path = Path(__file__).parent / "strategy_tuning_space.json"
    space = json.loads(space_path.read_text())
    return space["objective"]


def _fake_input_schema() -> dict:
    """Simulate a live TV input schema for validation tests."""
    return {
        "ZigZag Deviation (manual)": {
            "id": "in_1", "name": "ZigZag Deviation (manual)",
            "type": "float", "min": 3.0, "max": 10.0,
        },
        "Fallback Stop Family": {
            "id": "in_11", "name": "Fallback Stop Family",
            "type": "text",
            "options": ["FIB_NEG_0236", "FIB_NEG_0382", "ATR_1_0", "ATR_1_5",
                        "ATR_STRUCTURE_1_25", "FIB_0236_ATR_COMPRESS_0_50"],
        },
        "Footprint Ticks Per Row": {
            "id": "in_13", "name": "Footprint Ticks Per Row",
            "type": "integer", "min": 1, "max": 100,
        },
        "Enable Debug Logs": {
            "id": "in_25", "name": "Enable Debug Logs", "type": "bool",
        },
        "Show Footprint Audit Table": {
            "id": "in_26", "name": "Show Footprint Audit Table", "type": "bool",
        },
        "Target Line Lookback Bars": {
            "id": "in_22", "name": "Target Line Lookback Bars",
            "type": "integer", "min": 5, "max": 100,
        },
    }


# ===========================================================================
# Phase B — score_trial
# ===========================================================================

class TestScoreTrial:
    """Pre-AG PF-first scoring logic with richness constraints."""

    def test_hard_reject_too_few_trades(self):
        m = _balanced_metrics(total=50)
        obj = _default_objective()
        result = tsp.score_trial(m, obj)
        assert result["objective_score"] is None
        assert result["insufficient_sample"] is True

    def test_hard_reject_no_shorts(self):
        m = _balanced_metrics(total=500)
        m["short"]["trades"] = 0
        m["long"]["trades"] = 500
        result = tsp.score_trial(m, _default_objective())
        assert result["objective_score"] is None
        assert result["insufficient_sample"] is True

    def test_hard_reject_no_longs(self):
        m = _balanced_metrics(total=500)
        m["long"]["trades"] = 0
        m["short"]["trades"] = 500
        result = tsp.score_trial(m, _default_objective())
        assert result["objective_score"] is None

    def test_perfect_balanced_sample_scores_high(self):
        m = _balanced_metrics(total=2200, years=6)
        result = tsp.score_trial(m, _default_objective())
        assert result["objective_score"] is not None
        assert result["objective_score"] >= 0.6
        c = result["components"]
        assert c["sample_richness"] == 1.0
        assert c["directional_balance"] == 1.0
        assert c["regime_coverage"] == 1.0
        assert c["realism_ok"] is True

    def test_imbalanced_direction_scores_lower(self):
        m = _balanced_metrics(total=1000)
        m["long"]["trades"] = 900
        m["short"]["trades"] = 100
        result = tsp.score_trial(m, _default_objective())
        assert result["objective_score"] is not None
        assert result["components"]["directional_balance"] < 0.5

    def test_few_years_scores_lower_coverage(self):
        m = _balanced_metrics(total=1000, years=2)
        result = tsp.score_trial(m, _default_objective())
        c = result["components"]
        assert c["regime_coverage"] < 0.5

    def test_realism_gate_penalizes_high_pf(self):
        m = _balanced_metrics(total=1000, pf=5.0, net=50000)
        result = tsp.score_trial(m, _default_objective())
        assert result["components"]["realism_ok"] is False
        # Score should be roughly half of what it'd be without penalty
        m2 = _balanced_metrics(total=1000, pf=1.5, net=5000)
        result2 = tsp.score_trial(m2, _default_objective())
        assert result["objective_score"] < result2["objective_score"]

    def test_realism_gate_penalizes_low_pf(self):
        m = _balanced_metrics(total=1000, pf=0.4, net=-2000)
        result = tsp.score_trial(m, _default_objective())
        assert result["components"]["realism_ok"] is False

    def test_higher_pf_scores_higher_with_same_richness(self):
        low_pf = _balanced_metrics(total=1000, pf=0.9, net=-1000)
        high_pf = _balanced_metrics(total=1000, pf=1.5, net=1000)
        low_result = tsp.score_trial(low_pf, _default_objective())
        high_result = tsp.score_trial(high_pf, _default_objective())
        assert low_result["objective_score"] is not None
        assert high_result["objective_score"] is not None
        assert high_result["objective_score"] > low_result["objective_score"]

    def test_pf_none_does_not_crash(self):
        """PF=None (no losses) should not raise."""
        m = _balanced_metrics(total=500)
        m["profit_factor"] = None
        m["losses"] = 0
        m["wins"] = 500
        result = tsp.score_trial(m, _default_objective())
        assert result["objective_score"] is not None

    def test_pf_inf_does_not_crash(self):
        m = _balanced_metrics(total=500)
        m["profit_factor"] = math.inf
        result = tsp.score_trial(m, _default_objective())
        assert result["objective_score"] is not None

    def test_component_weights_sum_to_one(self):
        obj = _default_objective()
        w = obj["weights"]
        component_sum = (
            w["profit_factor"] + w["expectancy"] +
            w["sample_richness"] + w["directional_balance"]
            + w["regime_coverage"] + w["outcome_diversity"]
        )
        assert abs(component_sum - 1.0) < 0.001

    def test_score_is_between_zero_and_one(self):
        """Score should always be in [0, 1] for valid inputs."""
        for total in [200, 500, 1000, 2200]:
            for pf in [0.8, 1.0, 1.5, 2.5]:
                m = _balanced_metrics(total=total, pf=pf, net=total * 2)
                result = tsp.score_trial(m, _default_objective())
                if result["objective_score"] is not None:
                    assert 0.0 <= result["objective_score"] <= 1.0, (
                        f"score {result['objective_score']} out of range "
                        f"for total={total} pf={pf}"
                    )


# ===========================================================================
# Phase C — failure classification
# ===========================================================================

class TestFailureClassification:

    def test_no_recalc(self):
        assert tva.classify_failure_reason(
            RuntimeError("failed_no_recalc: never entered loading")
        ) == "no_recalc"

    def test_schema_drift(self):
        assert tva.classify_failure_reason(
            RuntimeError("schema_drift: 'Foo' not in live schema")
        ) == "schema_drift"

    def test_invalid_input(self):
        assert tva.classify_failure_reason(
            RuntimeError("invalid_input: value out of range")
        ) == "invalid_input"

    def test_compile_error(self):
        assert tva.classify_failure_reason(
            RuntimeError("compile_error: JS exception: blah")
        ) == "compile_error"

    def test_unknown_defaults_to_tv_disconnected(self):
        assert tva.classify_failure_reason(
            ConnectionError("websocket closed")
        ) == "tv_disconnected"

    def test_generic_runtime_error_defaults_to_disconnected(self):
        assert tva.classify_failure_reason(
            RuntimeError("something unexpected")
        ) == "tv_disconnected"


# ===========================================================================
# Phase A — input validation
# ===========================================================================

class TestValidateTrialParams:

    def test_valid_params_no_errors(self):
        schema = _fake_input_schema()
        params = {
            "ZigZag Deviation (manual)": 5.0,
            "Fallback Stop Family": "ATR_1_0",
        }
        errors = tva.validate_trial_params(params, schema)
        assert errors == []

    def test_unknown_param_is_schema_drift(self):
        schema = _fake_input_schema()
        params = {"Nonexistent Input": 42}
        errors = tva.validate_trial_params(params, schema)
        assert len(errors) == 1
        assert "schema_drift" in errors[0]

    def test_out_of_range_float_low(self):
        schema = _fake_input_schema()
        params = {"ZigZag Deviation (manual)": 1.0}  # min is 3.0
        errors = tva.validate_trial_params(params, schema)
        assert len(errors) == 1
        assert "invalid_input" in errors[0]

    def test_out_of_range_float_high(self):
        schema = _fake_input_schema()
        params = {"ZigZag Deviation (manual)": 99.0}  # max is 10.0
        errors = tva.validate_trial_params(params, schema)
        assert len(errors) == 1
        assert "invalid_input" in errors[0]

    def test_invalid_enum_value(self):
        schema = _fake_input_schema()
        params = {"Fallback Stop Family": "INVALID_STOP"}
        errors = tva.validate_trial_params(params, schema)
        assert len(errors) == 1
        assert "invalid_input" in errors[0]
        assert "INVALID_STOP" in errors[0]

    def test_valid_enum_value(self):
        schema = _fake_input_schema()
        params = {"Fallback Stop Family": "FIB_NEG_0382"}
        errors = tva.validate_trial_params(params, schema)
        assert errors == []

    def test_multiple_errors_accumulated(self):
        schema = _fake_input_schema()
        params = {
            "Nonexistent": 1,
            "ZigZag Deviation (manual)": 0.5,
            "Fallback Stop Family": "BAD",
        }
        errors = tva.validate_trial_params(params, schema)
        assert len(errors) == 3


# ===========================================================================
# Phase A — input value building
# ===========================================================================

class TestBuildInputValues:

    def test_resolves_names_to_ids(self):
        schema = _fake_input_schema()
        search = {"ZigZag Deviation (manual)": 7.0}
        locked = {"Footprint Ticks Per Row": 5}
        result = tva.build_input_values(search, locked, schema)
        ids = {r["id"] for r in result}
        # Should have the two params + debug force-offs
        assert "in_1" in ids   # ZigZag Deviation
        assert "in_13" in ids  # Footprint Ticks Per Row
        assert "in_25" in ids  # Enable Debug Logs (forced off)
        assert "in_26" in ids  # Show Footprint Audit Table (forced off)

    def test_search_overrides_locked(self):
        schema = _fake_input_schema()
        locked = {"ZigZag Deviation (manual)": 5.0}
        search = {"ZigZag Deviation (manual)": 8.0}
        result = tva.build_input_values(search, locked, schema)
        zigzag = next(r for r in result if r["id"] == "in_1")
        assert zigzag["value"] == 8.0

    def test_debug_outputs_forced_off(self):
        schema = _fake_input_schema()
        result = tva.build_input_values({}, {}, schema)
        debug = next(r for r in result if r["id"] == "in_25")
        table = next(r for r in result if r["id"] == "in_26")
        assert debug["value"] is False
        assert table["value"] is False

    def test_unknown_params_skipped(self):
        schema = _fake_input_schema()
        search = {"Ghost Param": 42}
        result = tva.build_input_values(search, {}, schema)
        ids = {r["id"] for r in result}
        # Only debug force-offs, Ghost Param skipped
        assert ids == {"in_25", "in_26"}


# ===========================================================================
# Phase A — values_match (loose equality)
# ===========================================================================

class TestValuesMatch:

    def test_exact_match(self):
        assert tva._values_match(5, 5) is True

    def test_float_precision(self):
        assert tva._values_match(1.0000000001, 1.0) is True

    def test_float_mismatch(self):
        assert tva._values_match(1.5, 2.5) is False

    def test_bool_match(self):
        assert tva._values_match(True, True) is True

    def test_bool_mismatch(self):
        assert tva._values_match(True, False) is False

    def test_string_match(self):
        assert tva._values_match("ATR_1_5", "ATR_1_5") is True

    def test_string_mismatch(self):
        assert tva._values_match("ATR_1_5", "ATR_1_0") is False

    def test_int_float_crosstype(self):
        assert tva._values_match(5, 5.0) is True


# ===========================================================================
# Phase A — metrics computation from TV trades
# ===========================================================================

class TestCalculateMetricsFromTV:

    def _make_trades(self, n_long=50, n_short=50, pnl_per=10.0):
        trades = []
        ts_base = 1700000000000  # ms
        cum = 0.0
        for i in range(n_long + n_short):
            side = "long" if i < n_long else "short"
            pnl = pnl_per if i % 3 != 0 else -pnl_per  # ~67% win rate
            cum += pnl
            trades.append({
                "trade_num": i + 1,
                "side": side,
                "entry_ts": ts_base + i * 60000,
                "exit_ts": ts_base + (i + 1) * 60000,
                "net_pnl": pnl,
                "cumulative_pnl": cum,
                "adverse_excursion_mag": abs(pnl) * 0.5,
                "favorable_excursion": abs(pnl) * 1.5,
            })
        return trades

    def test_basic_metrics_shape(self):
        trades = self._make_trades()
        m = tva.calculate_metrics_from_tv(trades, 10000, -37.50, "2025-01-01")
        assert m["total_trades"] == 100
        assert "long" in m
        assert "short" in m
        assert "by_year" in m
        assert "footprint_cohort" in m
        assert "profit_factor" in m

    def test_no_trades_raises(self):
        import pytest
        with pytest.raises(ValueError, match="No closed trades"):
            tva.calculate_metrics_from_tv([], 10000, -37.50, "2025-01-01")

    def test_long_short_split(self):
        trades = self._make_trades(n_long=60, n_short=40)
        m = tva.calculate_metrics_from_tv(trades, 10000, -37.50, "2025-01-01")
        assert m["long"]["trades"] == 60
        assert m["short"]["trades"] == 40

    def test_adverse_excursion_negated(self):
        """TV gives positive magnitude; metrics should negate for survival check."""
        trades = self._make_trades(n_long=1, n_short=0)
        # Internal: closed[0]["adverse_excursion"] should be negative
        # We verify indirectly via survival — if mag is 5 and stop is -37.50,
        # -5 > -37.50 is True, so survival should be 100%
        m = tva.calculate_metrics_from_tv(trades, 10000, -37.50, "2025-01-01")
        assert m["survival_30_tick_pct"] == 100.0


# ===========================================================================
# Structural — CLI and JSON
# ===========================================================================

class TestCLIStructure:

    def test_tv_auto_tune_has_preflight_and_run(self):
        p = tva.build_parser()
        choices = p._subparsers._group_actions[0].choices
        assert "preflight" in choices
        assert "run" in choices

    def test_run_has_required_flags(self):
        p = tva.build_parser()
        run_p = p._subparsers._group_actions[0].choices["run"]
        dests = {a.dest for a in run_p._actions}
        for flag in ["batch_dir", "trial_file", "recalc_timeout", "stop_on_error", "delay"]:
            assert flag in dests, f"missing --{flag.replace('_', '-')}"

    def test_tune_strategy_params_leaderboard_has_include_failed(self):
        p = tsp.build_parser()
        lb_p = p._subparsers._group_actions[0].choices["leaderboard"]
        opts = [a.option_strings for a in lb_p._actions]
        assert any("--include-failed" in o for o in opts)

    def test_tuning_space_json_valid(self):
        space_path = Path(__file__).parent / "strategy_tuning_space.json"
        space = json.loads(space_path.read_text())
        assert space["profile_name"] == "mes15m_agfit_v2"
        w = space["objective"]["weights"]
        expected_keys = {
            "profit_factor", "expectancy",
            "sample_richness", "directional_balance",
            "regime_coverage", "outcome_diversity", "realism_gate_penalty",
        }
        assert set(w.keys()) == expected_keys
        component_sum = (
            w["profit_factor"] + w["expectancy"] +
            w["sample_richness"] + w["directional_balance"] +
            w["regime_coverage"] + w["outcome_diversity"]
        )
        assert abs(component_sum - 1.0) < 0.001
        assert "profit_factor_range" in space["objective"]
        assert "expectancy_per_trade" in space["objective"]
        assert "side_profit_factor_floor" in space["objective"]

    def test_tuning_space_trade_bounds_use_min_max(self):
        space_path = Path(__file__).parent / "strategy_tuning_space.json"
        space = json.loads(space_path.read_text())
        bounds = space["objective"]["trade_count_bounds"]
        assert "min" in bounds
        assert "max" in bounds


# ===========================================================================
# Structural — evaluation_mode consistency
# ===========================================================================

class TestEvaluationModeConsistency:

    def test_successful_trials_use_tv_mcp_strict(self):
        """make_tv_trial_record should stamp TV_MCP_STRICT, not CSV_FULL."""
        src = Path(__file__).parent / "tv_auto_tune.py"
        content = src.read_text()
        # The function make_tv_trial_record should have TV_MCP_STRICT
        idx = content.index("def make_tv_trial_record")
        # Find the next "def " after it to bound the function
        next_def = content.index("\ndef ", idx + 1)
        fn_body = content[idx:next_def]
        assert '"TV_MCP_STRICT"' in fn_body, (
            "make_tv_trial_record should use TV_MCP_STRICT, not CSV_FULL"
        )
        assert '"CSV_FULL"' not in fn_body, (
            "make_tv_trial_record should not use CSV_FULL"
        )

    def test_failed_trials_use_tv_mcp_strict(self):
        """upsert_failed_trial SQL should use TV_MCP_STRICT."""
        src = Path(__file__).parent / "tune_strategy_params.py"
        content = src.read_text()
        idx = content.index("def upsert_failed_trial")
        next_def = content.index("\ndef ", idx + 1)
        fn_body = content[idx:next_def]
        assert "TV_MCP_STRICT" in fn_body


# ===========================================================================
# Structural — no hardcoded entity ID or static input map
# ===========================================================================

class TestNoHardcodedValues:

    def test_no_hardcoded_entity_id(self):
        """Regression: STRATEGY_ENTITY_ID = "kGnTgb" must not exist."""
        src = Path(__file__).parent / "tv_auto_tune.py"
        content = src.read_text()
        assert 'STRATEGY_ENTITY_ID = "kGnTgb"' not in content

    def test_no_static_input_map_as_live_code(self):
        """INPUT_NAME_TO_ID should not exist as an active dict assignment."""
        src = Path(__file__).parent / "tv_auto_tune.py"
        lines = src.read_text().splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert "INPUT_NAME_TO_ID: dict" not in stripped, (
                f"Static INPUT_NAME_TO_ID still present as live code at line {i+1}"
            )


# ===========================================================================
# Ripple-effect guards — issues found during integration review
# ===========================================================================

class TestInsufficientSampleGuard:
    """Hard-rejected trials must not silently become RECORDED rows."""

    def test_cdp_path_raises_on_insufficient_sample(self):
        """make_tv_trial_record raises ValueError when sample is insufficient."""
        import pytest
        # Build minimal inputs that produce < 200 trades
        trades = TestCalculateMetricsFromTV()._make_trades(n_long=10, n_short=10)
        space = json.loads(
            (Path(__file__).parent / "strategy_tuning_space.json").read_text()
        )
        config = {
            "trial_id": "test-reject",
            "search_parameters": {},
            "locked_parameters": {},
            "runtime_context": space.get("runtime_context", {}),
        }
        with pytest.raises(ValueError, match="insufficient sample"):
            tva.make_tv_trial_record(
                config=config,
                tv_trades=trades,
                space=space,
                initial_capital=10000,
                survival_stop_usd=-37.50,
                notes="test",
            )

    def test_cdp_path_succeeds_with_sufficient_sample(self):
        """make_tv_trial_record returns a record when sample is sufficient."""
        trades = TestCalculateMetricsFromTV()._make_trades(n_long=150, n_short=150)
        space = json.loads(
            (Path(__file__).parent / "strategy_tuning_space.json").read_text()
        )
        config = {
            "trial_id": "test-ok",
            "search_parameters": {},
            "locked_parameters": {},
            "runtime_context": space.get("runtime_context", {}),
        }
        record = tva.make_tv_trial_record(
            config=config,
            tv_trades=trades,
            space=space,
            initial_capital=10000,
            survival_stop_usd=-37.50,
            notes="test",
        )
        assert record["trial_id"] == "test-ok"
        assert record["evaluation_mode"] == "TV_MCP_STRICT"
        assert record["objective"]["objective_score"] is not None


class TestCsvMetaKeyNames:
    """CDP csv_meta must use start_date/end_date to match validate_csv_window."""

    def test_make_tv_trial_record_uses_start_date_key(self):
        """Regression: csv_meta must have 'start_date', not 'from_date'."""
        trades = TestCalculateMetricsFromTV()._make_trades(n_long=150, n_short=150)
        space = json.loads(
            (Path(__file__).parent / "strategy_tuning_space.json").read_text()
        )
        config = {
            "trial_id": "test-keys",
            "search_parameters": {},
            "locked_parameters": {},
            "runtime_context": space.get("runtime_context", {}),
        }
        record = tva.make_tv_trial_record(
            config=config,
            tv_trades=trades,
            space=space,
            initial_capital=10000,
            survival_stop_usd=-37.50,
            notes="test",
        )
        csv_meta = record["runtime_context"]["csv_meta"]
        assert "start_date" in csv_meta, f"csv_meta uses wrong key: {list(csv_meta.keys())}"
        assert "end_date" in csv_meta, f"csv_meta uses wrong key: {list(csv_meta.keys())}"
        assert "from_date" not in csv_meta, "csv_meta should not have from_date"


class TestUpsertFailedTrialConflict:
    """upsert_failed_trial ON CONFLICT must update evaluation_mode."""

    def test_upsert_failed_updates_evaluation_mode(self):
        src = Path(__file__).parent / "tune_strategy_params.py"
        content = src.read_text()
        idx = content.index("def upsert_failed_trial")
        next_def = content.index("\ndef ", idx + 1)
        fn_body = content[idx:next_def]
        # The ON CONFLICT clause must include evaluation_mode in its SET list
        conflict_idx = fn_body.index("ON CONFLICT")
        set_clause = fn_body[conflict_idx:]
        assert "evaluation_mode" in set_clause, (
            "upsert_failed_trial ON CONFLICT must update evaluation_mode "
            "to prevent stale PENDING mode on pre-existing rows"
        )


class TestJsonlHistorySesBothModes:
    """JSONL history must see both CSV_FULL and TV_MCP_STRICT trials."""

    def test_load_trials_jsonl_csv_full_includes_tv_mcp_strict(self):
        import tempfile
        ledger = Path(tempfile.mktemp(suffix=".jsonl"))
        try:
            # Write one CSV_FULL and one TV_MCP_STRICT trial
            tsp.append_trial_jsonl(ledger, {
                "trial_id": "csv-001", "evaluation_mode": "CSV_FULL",
                "search_parameters": {"a": 1},
            })
            tsp.append_trial_jsonl(ledger, {
                "trial_id": "cdp-001", "evaluation_mode": "TV_MCP_STRICT",
                "search_parameters": {"b": 2},
            })
            tsp.append_trial_jsonl(ledger, {
                "trial_id": "pending-001", "evaluation_mode": "PENDING",
                "search_parameters": {"c": 3},
            })
            trials = tsp.load_trials_jsonl_csv_full(ledger)
            ids = {t["trial_id"] for t in trials}
            assert "csv-001" in ids, "CSV_FULL trial missing"
            assert "cdp-001" in ids, "TV_MCP_STRICT trial missing"
            assert "pending-001" not in ids, "PENDING trial should be excluded"
        finally:
            ledger.unlink(missing_ok=True)


class TestRenderMarkdownTableNullScore:
    """render_markdown_table must not crash on None objective_score."""

    def test_none_score_formats_as_na(self):
        rows = [{
            "trial_id": "test-001",
            "metrics": {
                "net_pnl": 0, "profit_factor": None,
                "max_drawdown_pct": 0, "survival_30_tick_pct": 0,
                "footprint_cohort": {"profit_factor": None},
            },
            "objective": {"objective_score": None},
            "search_parameters": {"foo": 1},
        }]
        table = tsp.render_markdown_table(rows)
        assert "na" in table
        # Should not raise TypeError

    def test_valid_score_formats_normally(self):
        rows = [{
            "trial_id": "test-002",
            "metrics": {
                "net_pnl": 1000, "profit_factor": 1.5,
                "max_drawdown_pct": 5.0, "survival_30_tick_pct": 80.0,
                "footprint_cohort": {"profit_factor": 1.3},
            },
            "objective": {"objective_score": 0.8512},
            "search_parameters": {"bar": 2},
        }]
        table = tsp.render_markdown_table(rows)
        assert "0.8512" in table
