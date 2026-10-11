"""Chronological train/calibrate/select/test. Test period never enters selection."""
from __future__ import annotations
import json
import hashlib
import platform
from importlib.metadata import version
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score, brier_score_loss
from fraudopt.openml_source import PCA_COLUMNS
from fraudopt.policy import select_reviews, evaluate_policy, validate_costs
from fraudopt.diagnostics import write_diagnostics

FEATURES = [*PCA_COLUMNS, "log_amount"]


def split_chronologically(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Whole distinct timestamps stay together; avoid random split leakage."""
    d = df.sort_values("elapsed_seconds", kind="stable")
    if d["elapsed_seconds"].nunique() < 20:
        raise ValueError("Not enough distinct timestamps for temporal evaluation")
    # Quantiles on rows, assigned by strict boundaries (no shared timestamps).
    boundaries = np.quantile(d.elapsed_seconds.to_numpy(), [0.55, 0.70, 0.85])
    bounds = np.unique(boundaries)
    if len(bounds) != 3:
        raise ValueError("Unable to construct 4 separate time periods")
    b1, b2, b3 = bounds
    splits = {
        "train": d[d.elapsed_seconds < b1],
        "calibration": d[(d.elapsed_seconds >= b1) & (d.elapsed_seconds < b2)],
        "selection": d[(d.elapsed_seconds >= b2) & (d.elapsed_seconds < b3)],
        "test": d[d.elapsed_seconds >= b3],
    }
    for name, subset in splits.items():
        if len(subset) == 0 or subset.is_fraud.nunique() < 2:
            raise ValueError(f"{name} period lacks both classes; revise dataset/split")
    return splits


class Platt:
    """Simple sigmoid calibration fitted on held-out calibration period."""
    def __init__(self):
        self.model = LogisticRegression(max_iter=500)

    @staticmethod
    def transform(scores):
        scores = np.clip(np.asarray(scores, dtype=float), 1e-7, 1 - 1e-7)
        return np.log(scores / (1 - scores)).reshape(-1, 1)

    def fit(self, probabilities, labels):
        self.model.fit(self.transform(probabilities), labels)
        return self

    def predict_proba(self, probabilities):
        return self.model.predict_proba(self.transform(probabilities))[:, 1]


def score(model, calibrator, frame):
    raw = model.predict_proba(frame[FEATURES])[:, 1]
    return calibrator.predict_proba(raw)


def metrics(labels, probabilities):
    return {"average_precision": round(float(average_precision_score(labels, probabilities)), 6),
            "roc_auc": round(float(roc_auc_score(labels, probabilities)), 6),
            "brier_score": round(float(brier_score_loss(labels, probabilities)), 8),
            "fraud_prevalence": round(float(np.asarray(labels).mean()), 6)}


def run_training(clean_path: Path, output_dir: Path, capacity_per_day: int = 50,
                 review_cost: float = 10.0, friction_cost: float = 15.0,
                 effectiveness: float = 0.7, selection_metric: str = "average_precision") -> dict:
    validate_costs(review_cost, friction_cost, effectiveness)
    if selection_metric not in {"average_precision", "policy_utility"}:
        raise ValueError("Unknown selection metric")
    common = dict(capacity_per_day=capacity_per_day, review_cost=review_cost,
                  friction_cost=friction_cost, effectiveness=effectiveness)
    select_reviews([], [], [], **common)
    output_dir.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(clean_path)
    if not set([*FEATURES, "elapsed_seconds", "amount", "is_fraud"]).issubset(df.columns):
        raise ValueError("Missing expected cleaned model columns")
    splits = split_chronologically(df)
    candidates = {
        "logistic_regression": make_pipeline(StandardScaler(), LogisticRegression(
            class_weight="balanced", solver="lbfgs", max_iter=1000, random_state=42)),
        "gradient_boosting": HistGradientBoostingClassifier(
            learning_rate=0.06, max_iter=90, max_leaf_nodes=15,
            min_samples_leaf=40, l2_regularization=10, random_state=42),
    }
    records = {}
    for name, model in candidates.items():
        model.fit(splits["train"][FEATURES], splits["train"].is_fraud)
        cal_raw = model.predict_proba(splits["calibration"][FEATURES])[:, 1]
        calibrator = Platt().fit(cal_raw, splits["calibration"].is_fraud)
        selection_scores = score(model, calibrator, splits["selection"])
        selected = select_reviews(selection_scores, splits["selection"].amount,
                                  splits["selection"].elapsed_seconds, **common)
        policy = evaluate_policy(selected, splits["selection"].is_fraud,
                                 splits["selection"].amount, review_cost, friction_cost, effectiveness)
        records[name] = {"model": model, "calibrator": calibrator,
                         "selection_policy": policy, "selection_scores": selection_scores,
                         "selection_metrics": metrics(splits["selection"].is_fraud, selection_scores)}
    winner = max(records, key=lambda key: (
        records[key]["selection_policy"]["simulated_net_benefit_amount_units"]
        if selection_metric == "policy_utility" else
        records[key]["selection_metrics"]["average_precision"]))
    model, calibrator = records[winner]["model"], records[winner]["calibrator"]
    test = splits["test"]
    test_scores = score(model, calibrator, test)
    write_diagnostics(test.is_fraud, test_scores, output_dir)
    optimised = select_reviews(test_scores, test.amount, test.elapsed_seconds,
                               **common, rank_by="expected_value")
    threshold_like = select_reviews(test_scores, test.amount, test.elapsed_seconds,
                                    **common, rank_by="risk")
    policy_results = {
        "risk_only_top_k": evaluate_policy(threshold_like, test.is_fraud, test.amount, review_cost, friction_cost, effectiveness),
        "expected_value_top_k": evaluate_policy(optimised, test.is_fraud, test.amount, review_cost, friction_cost, effectiveness),
    }
    sensitivity = []
    validation = splits["selection"]
    for cost in sorted(set([review_cost * 0.5, review_cost, review_cost * 2])):
        for effect in sorted(set([effectiveness * 0.5, effectiveness, min(1.0, effectiveness * 1.5)])):
            flags = select_reviews(records[winner]["selection_scores"], validation.amount,
                                   validation.elapsed_seconds, capacity_per_day, cost, friction_cost, effect)
            sensitivity.append({"review_cost": cost, "effectiveness": effect,
                                **evaluate_policy(flags, validation.is_fraud, validation.amount,
                                                  cost, friction_cost, effect)})
    # No result here proves realised prevented loss; utility is counterfactual simulation.
    report = {
        "dataset": "ULB 2013/OpenML #43627 historical snapshot",
        "reproducibility": {"python": platform.python_version(),
                            "dependencies": {name: version(name) for name in
                                ("numpy", "pandas", "scikit-learn", "scipy", "requests", "joblib", "pyarrow", "matplotlib")},
                            "sha256_clean_file": hashlib.sha256(clean_path.read_bytes()).hexdigest()},
        "selection_metric": selection_metric,
        "candidate_validation_policies": {key: value["selection_policy"] for key, value in records.items()},
        "validation_cost_sensitivity": sensitivity,
        "period_time_ranges": {key: {"start_seconds": float(value.elapsed_seconds.min()),
                                    "end_seconds": float(value.elapsed_seconds.max()),
                                    "observed_span_seconds": float(value.elapsed_seconds.max() - value.elapsed_seconds.min())}
                               for key, value in splits.items()},
        "period_rows": {key: len(value) for key, value in splits.items()},
        "period_fraud": {key: int(value.is_fraud.sum()) for key, value in splits.items()},
        "candidates_selection_only": {key: value["selection_metrics"] for key, value in records.items()},
        "chosen_model": winner, "untouched_test_metrics": metrics(test.is_fraud, test_scores),
        "simulated_policy_assumptions": {"review_cost_amount_units": review_cost,
                   "false_review_friction_amount_units": friction_cost,
                   "intervention_effectiveness": effectiveness,
                   "capacity_per_simulated_day": capacity_per_day,
                   "capacity_semantics": "Offline whole-day ranking; full capacity for each touched elapsed-day bucket, including partial days"},
        "policy_test_comparison": policy_results,
        "caveats": ["Dataset is historical and static, not live fraud.",
                    "Currency and intervention effectiveness are not verified; results are illustrative.",
                    "Only anonymous PCA columns and amount are available, not account history.",
                    "Only one untouched chronological test evaluation is produced per run."]
    }
    joblib.dump({"model": model, "calibrator": calibrator, "features": FEATURES,
                 "model_name": winner}, output_dir / "model.joblib")
    (output_dir / "model_report.json").write_text(json.dumps(report, indent=2))
    pd.DataFrame({"elapsed_seconds": test.elapsed_seconds.to_numpy(), "amount": test.amount.to_numpy(),
                  "true_label": test.is_fraud.to_numpy(), "fraud_risk": test_scores,
                  "review_by_optimiser": optimised, "review_by_risk_only": threshold_like
                  }).to_csv(output_dir / "test_predictions.csv.gz", index=False, compression="gzip")
    return report
