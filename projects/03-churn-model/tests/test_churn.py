import numpy as np
import pandas as pd
import pytest
from churn.artifacts import ModelIntegrityError, load_verified_model, save_model
from churn.features import FEATURES, TARGET, build_preprocessor
from churn.generate import generate
from churn.train import choose_threshold, expected_value, train


def test_generator_is_deterministic_and_realistic():
    a, b = generate(n=1000, seed=1), generate(n=1000, seed=1)
    pd.testing.assert_frame_equal(a, b)
    assert 0.10 < a[TARGET].mean() < 0.35
    assert a["total_charges"].isna().any()  # new customers have no billing yet
    # The planted effect is present: month-to-month churns most.
    rates = a.groupby("contract")[TARGET].mean()
    assert rates["month-to-month"] > rates["one-year"] > rates["two-year"]


def test_preprocessor_handles_missing_and_unseen_values():
    df = generate(n=300, seed=2)
    prep = build_preprocessor().fit(df[FEATURES])
    odd = df[FEATURES].head(2).copy()
    odd["contract"] = "three-year"  # never seen in training
    odd["monthly_charges"] = np.nan
    out = prep.transform(odd)
    assert out.shape[0] == 2
    assert not np.isnan(out).any()


def test_expected_value_and_threshold():
    y = np.array([1, 0, 1, 0])
    p = np.array([0.9, 0.8, 0.4, 0.1])
    # contact the top two: one churner saved (0.3 * 600) minus two offers (2 * 40)
    assert expected_value(y, p, 0.5) == pytest.approx(0.3 * 600 - 2 * 40)
    assert 0.05 <= choose_threshold(y, p) <= 0.95


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    out = tmp_path_factory.mktemp("churn")
    return out, train(out, n=2500, seed=3)


def test_training_beats_baseline_and_writes_artifacts(trained):
    out, meta = trained
    assert meta["test_metrics"]["roc_auc"] > 0.75
    best_ap = meta["cv_results"][meta["model_name"]]["avg_precision_mean"]
    assert best_ap > meta["cv_results"]["baseline_majority"]["avg_precision_mean"] + 0.15
    assert meta["test_metrics"]["expected_value_usd"] > 0
    for name in ["model.joblib", "metadata.json", "roc_pr_curves.png", "calibration.png",
                 "feature_importance.png", "threshold_value.png"]:  # fmt: skip
        assert (out / name).exists()


def test_verified_load_round_trip(trained):
    out, meta = trained
    model, loaded_meta = load_verified_model(out)
    assert loaded_meta["model_name"] == meta["model_name"]
    assert len(loaded_meta["sha256"]) == 64
    proba = model.predict_proba(generate(n=5, seed=9)[FEATURES])[:, 1]
    assert ((proba >= 0) & (proba <= 1)).all()


def test_tampered_model_is_refused(tmp_path):
    save_model({"pretend": "model"}, {"note": "test"}, tmp_path)
    with (tmp_path / "model.joblib").open("ab") as fh:
        fh.write(b"tampered")
    with pytest.raises(ModelIntegrityError):
        load_verified_model(tmp_path)
