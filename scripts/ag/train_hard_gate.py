#!/usr/bin/env python3
"""Hard-gated AutoGluon training launcher for Warbird.

This command is the strict path to train + SHAP + Monte Carlo.
It blocks on any integrity breach across:
- preflight contracts (schema/data floor/zoo/trainer safeguards)
- post-training lineage/zoo/class-coverage checks
- SHAP artifact integrity
- Monte Carlo artifact integrity (including Task E degradation)

Exit code is non-zero on any breach.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.ag.train_ag_baseline as baseline

RUN_ID_RE = re.compile(r"agtrain_[0-9]{8}T[0-9]+Z")

CANONICAL_ZOO_FAMILIES = {"GBM", "CAT", "XGB", "RF", "XT", "NN_TORCH", "FASTAI"}

REQUIRED_TOPLEVEL_FILES = [
    "command.txt",
    "dataset_summary.json",
    "feature_manifest.json",
    "git_hash.txt",
    "pip_freeze.txt",
    "run_config.json",
    "run_status.json",
    "training_summary.json",
]

REQUIRED_SHAP_FILES = [
    "overall_importance.csv",
    "per_class_importance.csv",
    "temporal_stability.csv",
    "calibration_check.csv",
    "drop_candidates.csv",
    "summary.md",
    "manifest.json",
    "diagnostic_shap_manifest.json",
]

REQUIRED_MC_FILES = [
    "summary.md",
    "task_A.json",
    "task_B.json",
    "task_C.json",
    "task_D.json",
    "task_E_entry_rules.json",
    "task_F_tp_ladder.json",
    "task_G_calibration.json",
    "task_H_regime_stability.json",
    "task_I_win_profile.json",
]

TRAINER_REQUIRED_MARKERS = [
    "allow_exact_matches=False",
    "missing_families",
    "model-lineage mismatch",
    "command.txt",
    "pip_freeze.txt",
    "run_status.json",
]

STALE_SHAP_NOTE = "Source run used internal AutoGluon IID bagging/stacking and is not promotion-safe."
STALE_MC_NOTE = "Source run flagged for IID bag leakage and GBM-only model zoo."

BANNED_TRAIN_FLAGS = [
    "--allow-single-class-eval",
    "--allow-partial-class-coverage",
    "--allow-unsafe-internal-ensembling",
    "--num-bag-folds",
    "--num-stack-levels",
    "--dynamic-stacking",
    "--excluded-model-types",
]


class GateError(RuntimeError):
    pass


@dataclass
class RunIntegrity:
    has_internal_ensembling: bool
    missing_families_by_fold: dict[str, list[str]]
    lineage_failures: dict[str, str]
    partial_class_folds: list[str]

    @property
    def passed(self) -> bool:
        return (
            (not self.has_internal_ensembling)
            and (not self.missing_families_by_fold)
            and (not self.lineage_failures)
            and (not self.partial_class_folds)
        )


def canonical_family_for_model(model_name: str | None) -> str | None:
    if not model_name:
        return None
    name = str(model_name)
    if name.startswith("LightGBM"):
        return "GBM"
    if name.startswith("CatBoost"):
        return "CAT"
    if name.startswith("XGBoost"):
        return "XGB"
    if name.startswith("RandomForest"):
        return "RF"
    if name.startswith("ExtraTrees"):
        return "XT"
    if name.startswith("NeuralNetTorch"):
        return "NN_TORCH"
    if name.startswith("NeuralNetFastAI") or "FastAI" in name:
        return "FASTAI"
    return None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def run_and_stream(cmd: list[str], *, cwd: Path) -> list[str]:
    print(f"\n$ {shlex.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        print(line, end="")
        lines.append(line.rstrip("\n"))
    rc = proc.wait()
    if rc != 0:
        raise GateError(f"Command failed with exit code {rc}: {shlex.join(cmd)}")
    return lines


def run_quiet(cmd: list[str], *, cwd: Path) -> None:
    print(f"\n$ {shlex.join(cmd)}")
    rc = subprocess.run(cmd, cwd=str(cwd), check=False).returncode
    if rc != 0:
        raise GateError(f"Command failed with exit code {rc}: {shlex.join(cmd)}")


def normalize_passthrough_args(train_passthrough: list[str]) -> list[str]:
    passthrough = list(train_passthrough)
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    for tok in passthrough:
        for banned in BANNED_TRAIN_FLAGS:
            if tok == banned or tok.startswith(f"{banned}="):
                raise GateError(
                    f"Refusing unsafe training override `{tok}`. "
                    "Use the hard-gated defaults (no internal ensembling, no partial-class bypass)."
                )
    return passthrough


def preflight(args: argparse.Namespace) -> None:
    print("\n[gate] preflight checks")
    run_quiet(["./scripts/guards/check-canonical-zoo.sh"], cwd=REPO_ROOT)

    trainer_path = REPO_ROOT / "scripts/ag/train_ag_baseline.py"
    trainer_text = trainer_path.read_text()
    for marker in TRAINER_REQUIRED_MARKERS:
        if marker not in trainer_text:
            raise GateError(f"Trainer safeguard marker missing: `{marker}` in {trainer_path}")

    shap_source = (REPO_ROOT / "scripts/ag/run_diagnostic_shap.py").read_text()
    mc_source = (REPO_ROOT / "scripts/ag/monte_carlo_run.py").read_text()
    if STALE_SHAP_NOTE in shap_source:
        raise GateError("SHAP script still contains stale hardcoded bagging warning text.")
    if STALE_MC_NOTE in mc_source:
        raise GateError("Monte Carlo script still contains stale hardcoded run-warning text.")

    with psycopg2.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ag_training_runs WHERE run_status='RUNNING'")
            running = int(cur.fetchone()[0])
            if running > 0:
                raise GateError(
                    f"Found {running} RUNNING rows in ag_training_runs. "
                    "Resolve orphan/stuck runs before launching a new training run."
                )

            cur.execute("SELECT count(*) FROM ag_training")
            row_count = int(cur.fetchone()[0])
            floor = int(baseline.EXPECTED_AG_TRAINING_ROWS_FLOOR)
            if row_count < floor:
                raise GateError(
                    f"ag_training row count {row_count:,} is below floor {floor:,}. "
                    "Refusing to train on truncated data."
                )

    print("[gate] preflight passed")


def parse_run_id(lines: list[str]) -> str | None:
    found: str | None = None
    for line in lines:
        m = RUN_ID_RE.search(line)
        if m:
            found = m.group(0)
    return found


def newest_run_id(output_root: Path, *, started_at_utc: datetime) -> str | None:
    candidates: list[tuple[float, str]] = []
    for p in output_root.glob("agtrain_*"):
        if not p.is_dir():
            continue
        if not RUN_ID_RE.fullmatch(p.name):
            continue
        mtime = p.stat().st_mtime
        if mtime >= started_at_utc.timestamp() - 5:
            candidates.append((mtime, p.name))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def infer_run_integrity(run_dir: Path, fold_codes: list[str]) -> RunIntegrity:
    has_internal_ensembling = False
    missing_families_by_fold: dict[str, list[str]] = {}
    lineage_failures: dict[str, str] = {}
    partial_class_folds: list[str] = []

    for fold_code in fold_codes:
        fold_dir = run_dir / fold_code
        summary = load_json(fold_dir / "fold_summary.json")
        autogluon = summary.get("autogluon") or {}

        num_bag = int(autogluon.get("num_bag_folds") or 0)
        num_stack = int(autogluon.get("num_stack_levels") or 0)
        dynamic_stacking = str(autogluon.get("dynamic_stacking") or "").lower()
        if num_bag > 0 or num_stack > 0 or dynamic_stacking == "auto":
            has_internal_ensembling = True

        fams = set(autogluon.get("zoo_families_present") or [])
        missing = sorted(CANONICAL_ZOO_FAMILIES - fams)
        if missing:
            missing_families_by_fold[fold_code] = missing

        if summary.get("val_missing_labels") or summary.get("test_missing_labels"):
            partial_class_folds.append(fold_code)

        best_model = autogluon.get("best_model")
        test_macro = autogluon.get("test_macro_f1")
        leaderboard_path = fold_dir / "leaderboard.csv"
        if best_model and test_macro is not None and leaderboard_path.exists():
            rows = read_csv_rows(leaderboard_path)
            best_rows = [r for r in rows if str(r.get("model")) == str(best_model)]
            if not best_rows:
                lineage_failures[fold_code] = f"best_model_missing:{best_model}"
            else:
                try:
                    score_test = float(best_rows[0]["score_test"])
                    if abs(score_test - float(test_macro)) > 1e-6:
                        lineage_failures[fold_code] = (
                            f"score_test={score_test:.6f} test_macro_f1={float(test_macro):.6f}"
                        )
                except Exception as exc:
                    lineage_failures[fold_code] = f"lineage_parse_error:{exc}"

    return RunIntegrity(
        has_internal_ensembling=has_internal_ensembling,
        missing_families_by_fold=missing_families_by_fold,
        lineage_failures=lineage_failures,
        partial_class_folds=sorted(partial_class_folds),
    )


def validate_training_run(run_id: str, args: argparse.Namespace) -> tuple[Path, RunIntegrity]:
    print("\n[gate] validating training run artifacts and DB lineage")
    run_dir = Path(args.output_root) / run_id
    if not run_dir.exists():
        raise GateError(f"Run directory not found: {run_dir}")

    for rel in REQUIRED_TOPLEVEL_FILES:
        p = run_dir / rel
        if not p.exists():
            raise GateError(f"Missing required run artifact: {p}")

    run_status = load_json(run_dir / "run_status.json")
    if run_status.get("run_status") != "SUCCEEDED":
        raise GateError(f"Run status is not SUCCEEDED: {run_status}")

    training_summary = load_json(run_dir / "training_summary.json")
    fold_summaries = training_summary.get("folds") or []
    if not fold_summaries:
        raise GateError("training_summary.json has no folds.")
    fold_codes = [str(f["fold_code"]) for f in fold_summaries]

    for fold_code in fold_codes:
        fold_dir = run_dir / fold_code
        summary_path = fold_dir / "fold_summary.json"
        lb_path = fold_dir / "leaderboard.csv"
        log_path = fold_dir / "predictor/logs/predictor_log.txt"

        if not summary_path.exists() or not lb_path.exists() or not log_path.exists():
            raise GateError(f"Fold {fold_code} missing required artifacts.")

        summary = load_json(summary_path)
        autogluon = summary.get("autogluon") or {}
        best_model = autogluon.get("best_model")
        if not best_model:
            raise GateError(f"Fold {fold_code} missing autogluon.best_model")

        test_macro_f1 = autogluon.get("test_macro_f1")
        if test_macro_f1 is None:
            raise GateError(f"Fold {fold_code} missing autogluon.test_macro_f1")

        if summary.get("val_missing_labels") or summary.get("test_missing_labels"):
            raise GateError(
                f"Fold {fold_code} has class coverage gaps: "
                f"val_missing={summary.get('val_missing_labels')} "
                f"test_missing={summary.get('test_missing_labels')}"
            )

        fams = set(autogluon.get("zoo_families_present") or [])
        if fams != CANONICAL_ZOO_FAMILIES:
            raise GateError(
                f"Fold {fold_code} canonical zoo mismatch. expected={sorted(CANONICAL_ZOO_FAMILIES)} got={sorted(fams)}"
            )

        rows = read_csv_rows(lb_path)
        if len(rows) < 10:
            raise GateError(f"Fold {fold_code} leaderboard has only {len(rows)} models (<10).")

        model_names = [str(r.get("model") or "") for r in rows]
        fams_from_lb = {
            fam for model in model_names if (fam := canonical_family_for_model(model)) is not None
        }
        missing_lb = sorted(CANONICAL_ZOO_FAMILIES - fams_from_lb)
        if missing_lb:
            raise GateError(f"Fold {fold_code} leaderboard missing families: {missing_lb}")

        best_rows = [r for r in rows if str(r.get("model")) == str(best_model)]
        if not best_rows:
            raise GateError(f"Fold {fold_code} best_model `{best_model}` missing from leaderboard.csv")
        try:
            score_test = float(best_rows[0]["score_test"])
            if abs(score_test - float(test_macro_f1)) > 1e-6:
                raise GateError(
                    f"Fold {fold_code} lineage mismatch: best_model={best_model} "
                    f"score_test={score_test:.6f} test_macro_f1={float(test_macro_f1):.6f}"
                )
        except ValueError as exc:
            raise GateError(f"Fold {fold_code} score_test parse error: {exc}") from exc

        log_text = log_path.read_text(errors="ignore")
        if re.search(r"Not enough memory to train|skipped due to lack of memory", log_text, re.IGNORECASE):
            raise GateError(f"Fold {fold_code} predictor log contains memory-skip warnings.")

    integrity = infer_run_integrity(run_dir, fold_codes)
    if not integrity.passed:
        raise GateError(
            "Run integrity failed after training: "
            f"has_internal_ensembling={integrity.has_internal_ensembling} "
            f"missing_families_by_fold={integrity.missing_families_by_fold} "
            f"lineage_failures={integrity.lineage_failures} "
            f"partial_class_folds={integrity.partial_class_folds}"
        )

    with psycopg2.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT run_status, rows_total, feature_count, fold_count "
                "FROM ag_training_runs WHERE run_id=%s",
                (run_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise GateError(f"Run {run_id} missing in ag_training_runs")
            db_status, rows_total, feature_count, fold_count = row
            if db_status != "SUCCEEDED":
                raise GateError(f"DB run_status for {run_id} is {db_status}, expected SUCCEEDED")
            if int(fold_count or 0) != len(fold_codes):
                raise GateError(
                    f"DB fold_count mismatch for {run_id}: db={fold_count} expected={len(fold_codes)}"
                )

            cur.execute(
                "SELECT fold_code, metric_name, metric_value, model_name "
                "FROM ag_training_run_metrics "
                "WHERE run_id=%s AND split_code='test' AND metric_name='macro_f1' "
                "ORDER BY fold_code, model_name",
                (run_id,),
            )
            metric_rows = cur.fetchall()

    by_fold_non_baseline: dict[str, tuple[float, str]] = {}
    for fold_code, metric_name, metric_value, model_name in metric_rows:
        if model_name == "STOPPED":
            continue
        by_fold_non_baseline[str(fold_code)] = (float(metric_value), str(model_name))

    for fold in fold_summaries:
        fold_code = str(fold["fold_code"])
        summary = load_json(run_dir / fold_code / "fold_summary.json")
        autogluon = summary.get("autogluon") or {}
        db_metric = by_fold_non_baseline.get(fold_code)
        if db_metric is None:
            raise GateError(f"DB missing non-baseline test macro_f1 row for {fold_code}")
        db_value, db_model = db_metric
        fs_value = float(autogluon["test_macro_f1"])
        fs_model = str(autogluon["best_model"])
        if db_model != fs_model or abs(db_value - fs_value) > 1e-6:
            raise GateError(
                f"DB lineage mismatch for {fold_code}: db=({db_model},{db_value:.6f}) "
                f"summary=({fs_model},{fs_value:.6f})"
            )

    print("[gate] training validation passed")
    return run_dir, integrity


def choose_shap_model(run_dir: Path, *, preferred_prefix: str, strict: bool) -> str:
    model_sets: list[set[str]] = []
    for fold_dir in sorted(p for p in run_dir.glob("fold_*") if p.is_dir()):
        lb_path = fold_dir / "leaderboard.csv"
        rows = read_csv_rows(lb_path)
        model_sets.append({str(r.get("model") or "") for r in rows if r.get("model")})
    if not model_sets:
        raise GateError("No leaderboard sets found to choose SHAP model.")

    common_models = set.intersection(*model_sets)
    if not common_models:
        raise GateError("No common model name exists across all folds for SHAP.")

    if preferred_prefix and preferred_prefix.lower() != "auto":
        preferred = sorted(m for m in common_models if m.startswith(preferred_prefix))
        if preferred:
            return preferred[0]
        if strict:
            raise GateError(
                f"Preferred SHAP model prefix `{preferred_prefix}` is not present in all folds. "
                f"Common models: {sorted(common_models)}"
            )

    priority = [
        "LightGBM",
        "CatBoost",
        "XGBoost",
        "NeuralNetTorch",
        "NeuralNetFastAI",
        "RandomForest",
        "ExtraTrees",
    ]
    for prefix in priority:
        candidates = sorted(m for m in common_models if m.startswith(prefix))
        if candidates:
            return candidates[0]
    return sorted(common_models)[0]


def run_shap(run_id: str, run_dir: Path, integrity: RunIntegrity, args: argparse.Namespace) -> Path:
    print("\n[gate] running SHAP")
    model_name = choose_shap_model(
        run_dir,
        preferred_prefix=args.shap_model_prefix,
        strict=args.strict_shap_model,
    )
    print(f"[gate] SHAP model selected: {model_name}")

    cmd = [
        args.python_exec,
        "scripts/ag/run_diagnostic_shap.py",
        "--run-id",
        run_id,
        "--dsn",
        args.dsn,
        "--output-root",
        args.shap_output_root,
        "--model-name",
        model_name,
    ]
    run_and_stream(cmd, cwd=REPO_ROOT)

    shap_dir = Path(args.shap_output_root) / run_id
    for rel in REQUIRED_SHAP_FILES:
        p = shap_dir / rel
        if not p.exists():
            raise GateError(f"Missing SHAP artifact: {p}")

    diag_manifest = load_json(shap_dir / "diagnostic_shap_manifest.json")
    fold_artifacts = diag_manifest.get("fold_artifacts") or []
    if len(fold_artifacts) < 1:
        raise GateError("diagnostic_shap_manifest.json has no fold_artifacts")

    for fa in fold_artifacts:
        if int(fa.get("row_count", 0)) <= 0:
            raise GateError(f"Invalid SHAP fold artifact row_count: {fa}")
        if int(fa.get("feature_count", 0)) <= 0:
            raise GateError(f"Invalid SHAP fold artifact feature_count: {fa}")

    summary_text = (shap_dir / "summary.md").read_text()
    manifest_text = (shap_dir / "manifest.json").read_text()
    if integrity.passed and (STALE_SHAP_NOTE in summary_text or STALE_SHAP_NOTE in manifest_text):
        raise GateError("SHAP artifacts contain stale bagging warning for a clean run.")

    print("[gate] SHAP validation passed")
    return shap_dir


def run_monte_carlo(run_id: str, shap_dir: Path, integrity: RunIntegrity, args: argparse.Namespace) -> Path:
    print("\n[gate] running Monte Carlo")
    shap_artifact = shap_dir / "overall_importance.csv"
    cmd = [
        args.python_exec,
        "scripts/ag/monte_carlo_run.py",
        "--run-id",
        run_id,
        "--dsn",
        args.dsn,
        "--shap-artifact",
        str(shap_artifact),
        "--min-rule-n",
        str(args.min_rule_n),
        "--task-e-min-required-rules",
        str(args.task_e_min_required_rules),
    ]
    if args.no_macro:
        cmd.append("--no-macro")
    run_and_stream(cmd, cwd=REPO_ROOT)

    mc_dir = Path(args.output_root) / run_id / "monte_carlo"
    for rel in REQUIRED_MC_FILES:
        p = mc_dir / rel
        if not p.exists():
            raise GateError(f"Missing Monte Carlo artifact: {p}")

    task_e = load_json(mc_dir / "task_E_entry_rules.json")
    top_take = task_e.get("top_k_take") or {}
    top_avoid = task_e.get("top_k_avoid") or {}

    if len(top_take) < args.task_e_min_required_rules:
        raise GateError(
            f"Task E has only {len(top_take)} take rules (< {args.task_e_min_required_rules})."
        )
    if len(top_avoid) < args.task_e_min_required_rules:
        raise GateError(
            f"Task E has only {len(top_avoid)} avoid rules (< {args.task_e_min_required_rules})."
        )

    overlap = sorted(set(top_take).intersection(top_avoid))
    if overlap:
        raise GateError(f"Task E take/avoid overlap detected: {overlap[:5]}")

    if bool(task_e.get("degraded")):
        raise GateError(
            "Task E marked degraded=true. Rule surface is not stable enough for deployment decisions."
        )

    task_g = load_json(mc_dir / "task_G_calibration.json")
    calibration_rows = task_g.get("data") or []
    if len(calibration_rows) < args.min_task_g_rows:
        raise GateError(
            f"Task G calibration rows too small: {len(calibration_rows)} < {args.min_task_g_rows}"
        )

    task_h = load_json(mc_dir / "task_H_regime_stability.json")
    if "spearman_rho_ev_rank" not in task_h:
        raise GateError("Task H missing spearman_rho_ev_rank")
    if task_h.get("verdict") not in {"STABLE", "FRAGILE", "UNKNOWN"}:
        raise GateError(f"Task H verdict unexpected: {task_h.get('verdict')}")

    summary_text = (mc_dir / "summary.md").read_text()
    if integrity.passed and STALE_MC_NOTE in summary_text:
        raise GateError("Monte Carlo summary contains stale bagging/GBM-only warning for a clean run.")

    print("[gate] Monte Carlo validation passed")
    return mc_dir


def build_train_cmd(args: argparse.Namespace, passthrough: list[str]) -> list[str]:
    cmd = [
        args.python_exec,
        "scripts/ag/train_ag_baseline.py",
        "--output-root",
        args.output_root,
        "--time-limit",
        str(args.time_limit),
        "--num-bag-folds",
        "0",
        "--num-stack-levels",
        "0",
        "--dynamic-stacking",
        "off",
        "--excluded-model-types",
        "",
        "--ag-max-memory-usage-ratio",
        str(args.ag_max_memory_usage_ratio),
    ]
    if args.no_macro:
        cmd.append("--no-macro")
    if args.start_date:
        cmd.extend(["--start-date", args.start_date])
    if args.end_date:
        cmd.extend(["--end-date", args.end_date])
    if args.label_count_threshold is not None:
        cmd.extend(["--label-count-threshold", str(args.label_count_threshold)])
    cmd.extend(passthrough)
    return cmd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hard-gated train -> SHAP -> Monte Carlo pipeline. Blocks on integrity failures."
    )
    parser.add_argument("--dsn", default=baseline.DEFAULT_DSN)
    parser.add_argument("--python-exec", default=sys.executable)
    parser.add_argument("--output-root", default="artifacts/ag_runs")
    parser.add_argument("--shap-output-root", default="artifacts/shap")
    parser.add_argument("--time-limit", type=int, default=3600)
    parser.add_argument("--ag-max-memory-usage-ratio", type=float, default=2.5)
    parser.add_argument("--start-date", default=None)
    parser.add_argument("--end-date", default=None)
    parser.add_argument("--label-count-threshold", type=int, default=1)
    parser.add_argument("--no-macro", action="store_true")

    parser.add_argument("--shap-model-prefix", default="LightGBM")
    parser.add_argument("--strict-shap-model", action="store_true")

    parser.add_argument("--min-rule-n", type=int, default=50)
    parser.add_argument("--task-e-min-required-rules", type=int, default=10)
    parser.add_argument("--min-task-g-rows", type=int, default=20)
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run hard preflight checks and exit without launching training.",
    )

    parser.add_argument(
        "train_passthrough",
        nargs=argparse.REMAINDER,
        help="Extra args forwarded to train_ag_baseline.py after '--'. Unsafe overrides are blocked.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    passthrough = normalize_passthrough_args(args.train_passthrough)

    preflight(args)
    if args.preflight_only:
        print("\n[gate] preflight-only mode complete")
        return

    started_at_utc = datetime.now(UTC)
    train_cmd = build_train_cmd(args, passthrough)
    lines = run_and_stream(train_cmd, cwd=REPO_ROOT)

    run_id = parse_run_id(lines)
    if run_id is None:
        run_id = newest_run_id(Path(args.output_root), started_at_utc=started_at_utc)
    if run_id is None:
        raise GateError("Unable to resolve run_id from trainer output or output-root scan.")

    print(f"\n[gate] resolved run_id={run_id}")
    run_dir, integrity = validate_training_run(run_id, args)
    shap_dir = run_shap(run_id, run_dir, integrity, args)
    mc_dir = run_monte_carlo(run_id, shap_dir, integrity, args)

    print("\n[gate] PASS")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "run_dir": str(run_dir),
                "shap_dir": str(shap_dir),
                "monte_carlo_dir": str(mc_dir),
                "integrity_passed": integrity.passed,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except GateError as exc:
        print(f"\n[gate] BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2)
