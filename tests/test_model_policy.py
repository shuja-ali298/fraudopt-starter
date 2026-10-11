import numpy as np
import pandas as pd
from fraudopt.openml_source import PCA_COLUMNS
from fraudopt.model import split_chronologically, Platt
from fraudopt.policy import select_reviews, evaluate_policy


def test_time_boundaries_never_overlap():
    n = 500
    df = pd.DataFrame({"elapsed_seconds": np.repeat(np.arange(100), 5),
                       "is_fraud": np.tile([0, 0, 1, 0, 0], 100)})
    result = split_chronologically(df)
    assert sum(len(v) for v in result.values()) == n
    for a, b in zip(list(result.values())[:-1], list(result.values())[1:]):
        assert a.elapsed_seconds.max() < b.elapsed_seconds.min()


def test_policy_capacity_and_invalid_probabilities():
    p = np.array([0.99, 0.85, 0.7, 0.4, 0.9])
    amount = np.array([400, 300, 200, 100, 500])
    time = np.array([0, 100, 200, 300, 86400])
    chosen = select_reviews(p, amount, time, capacity_per_day=2)
    assert chosen[:4].sum() <= 2
    assert chosen[4] == 1
    result = evaluate_policy(chosen, [1, 0, 1, 0, 1], amount, 10, 15, .7)
    assert result["reviews"] == 3
    import pytest
    with pytest.raises(ValueError):
        select_reviews(np.array([1.2]), np.array([10]), np.array([1]))


def test_platt_probabilities_bounded():
    p = [0.01, 0.08, 0.1, 0.5, 0.8, 0.95]
    y = [0, 0, 0, 0, 1, 1]
    cal = Platt().fit(p, y)
    x = cal.predict_proba(p)
    assert np.all((x >= 0) & (x <= 1))
