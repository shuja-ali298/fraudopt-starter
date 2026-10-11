"""Small *artificial* dataset tests pipeline wiring, not fraud-model quality."""
import pytest
import numpy as np
import pandas as pd
from fraudopt.openml_source import PCA_COLUMNS
from fraudopt.model import run_training


@pytest.mark.parametrize("selection_metric", ["average_precision", "policy_utility"])
def test_training_and_policy_end_to_end(tmp_path, selection_metric):
    rng = np.random.default_rng(21)
    n = 900
    fraud = (rng.random(n) < 0.09).astype(int)
    data = {col: rng.standard_normal(n) for col in PCA_COLUMNS}
    data["V1"] = data["V1"] + fraud * 2
    amount = rng.gamma(2, 50, n)
    df = pd.DataFrame(data)
    df["elapsed_seconds"] = np.arange(n) * 140
    df["amount"] = amount
    df["log_amount"] = np.log1p(amount)
    df["is_fraud"] = fraud
    path = tmp_path / "clean.csv.gz"
    df.to_csv(path, index=False, compression="gzip")
    result = run_training(path, tmp_path / "out", capacity_per_day=20, selection_metric=selection_metric, review_cost=8, friction_cost=12, effectiveness=.6)
    assert set(result["candidates_selection_only"]) == {"gradient_boosting", "logistic_regression"}
    assert (tmp_path / "out" / "model.joblib").exists()
    assert (tmp_path / "out" / "test_predictions.csv.gz").exists()
    assert result["policy_test_comparison"]["expected_value_top_k"]["reviews"] <= 20

    assert result["selection_metric"] == selection_metric
    assert result["simulated_policy_assumptions"]["review_cost_amount_units"] == 8
    assert result["period_time_ranges"]["test"]["observed_span_seconds"] > 0
    assert len(result["reproducibility"]["sha256_clean_file"]) == 64
    policies = result["candidate_validation_policies"]
    if selection_metric == "policy_utility":
        assert policies[result["chosen_model"]]["simulated_net_benefit_amount_units"] == max(
            v["simulated_net_benefit_amount_units"] for v in policies.values())
    assert all(v["reviews"] <= 20 for v in result["validation_cost_sensitivity"])
    from xml.etree import ElementTree
    assert ElementTree.parse(tmp_path / "out" / "model_diagnostics.svg").getroot().tag.endswith('svg')
    assert pd.read_csv(tmp_path / "out" / "calibration_bins.csv").transactions.sum() == result["period_rows"]["test"]
