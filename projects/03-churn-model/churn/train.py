"""Train, compare, tune and evaluate churn models.

Run:  python -m churn.train --out-dir artifacts/churn

Protocol (no test-set leakage):
1. Hold out 20% as a test set, untouched until the very end.
2. Compare candidate models with 5-fold stratified cross-validation on the training set.
3. Pick the decision threshold from out-of-fold predictions on the training set.
4. Refit the chosen model on all training data, then evaluate once on the test set.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # render to files, no display needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from churn.artifacts import save_model
from churn.features import FEATURES, TARGET, build_preprocessor
from churn.generate import generate
from sklearn.calibration import calibration_curve
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import (
    StratifiedKFold,
    cross_val_predict,
    cross_validate,
    train_test_split,
)
from sklearn.pipeline import Pipeline

SEED = 42
# Business assumptions for choosing the threshold (documented in the model card).
CUSTOMER_VALUE = 600.0  # annual margin of a retained customer
SAVE_RATE = 0.30  # share of contacted would-be churners the offer actually keeps
OFFER_COST = 40.0  # cost of one retention offer


def candidate_models() -> dict[str, Pipeline]:
    def pipe(clf) -> Pipeline:
        return Pipeline([("prep", build_preprocessor()), ("clf", clf)])

    return {
        "baseline_majority": pipe(DummyClassifier(strategy="prior")),
        "logistic_regression": pipe(LogisticRegression(max_iter=2000, C=1.0)),
        "gradient_boosting": pipe(
            HistGradientBoostingClassifier(
                learning_rate=0.05, max_iter=300, max_leaf_nodes=15,
                early_stopping=True, random_state=SEED,
            )
        ),
    }  # fmt: skip


def expected_value(y_true: np.ndarray, proba: np.ndarray, threshold: float) -> float:
    """Net value of contacting everyone whose churn probability >= threshold."""
    contacted = proba >= threshold
    saved_value = (contacted & (y_true == 1)).sum() * SAVE_RATE * CUSTOMER_VALUE
    return float(saved_value - contacted.sum() * OFFER_COST)


def choose_threshold(y_true: np.ndarray, proba: np.ndarray) -> float:
    grid = np.round(np.arange(0.05, 0.95, 0.01), 2)
    values = [expected_value(y_true, proba, t) for t in grid]
    return float(grid[int(np.argmax(values))])


def save_figures(y_test, proba, threshold, model, x_test, out_dir: Path) -> dict:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    fpr, tpr, _ = roc_curve(y_test, proba)
    axes[0].plot(fpr, tpr, label=f"AUC = {roc_auc_score(y_test, proba):.3f}")
    axes[0].plot([0, 1], [0, 1], "--", color="grey")
    axes[0].set(title="ROC curve", xlabel="False positive rate", ylabel="True positive rate")
    axes[0].legend()
    prec, rec, _ = precision_recall_curve(y_test, proba)
    axes[1].plot(rec, prec, label=f"AP = {average_precision_score(y_test, proba):.3f}")
    axes[1].axhline(y_test.mean(), ls="--", color="grey", label="base rate")
    axes[1].set(title="Precision-recall curve", xlabel="Recall", ylabel="Precision")
    axes[1].legend()
    fig.tight_layout()
    fig.savefig(out_dir / "roc_pr_curves.png", dpi=120)
    plt.close(fig)

    frac_pos, mean_pred = calibration_curve(y_test, proba, n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot(mean_pred, frac_pos, "o-", label="model")
    ax.plot([0, 1], [0, 1], "--", color="grey", label="perfect")
    ax.set(title="Calibration", xlabel="Predicted probability", ylabel="Observed churn rate")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "calibration.png", dpi=120)
    plt.close(fig)

    imp = permutation_importance(
        model, x_test, y_test, scoring="average_precision", n_repeats=10, random_state=SEED
    )
    order = np.argsort(imp.importances_mean)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.barh(np.array(FEATURES)[order], imp.importances_mean[order],
            xerr=imp.importances_std[order])  # fmt: skip
    ax.set(title="Permutation importance (drop in average precision)")
    fig.tight_layout()
    fig.savefig(out_dir / "feature_importance.png", dpi=120)
    plt.close(fig)

    grid = np.arange(0.05, 0.95, 0.01)
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(grid, [expected_value(y_test, proba, t) for t in grid])
    ax.axvline(threshold, ls="--", color="red", label=f"chosen threshold = {threshold:.2f}")
    ax.set(title="Expected campaign value vs threshold (test set)", xlabel="Threshold",
           ylabel="Net value ($)")  # fmt: skip
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "threshold_value.png", dpi=120)
    plt.close(fig)

    return dict(zip(FEATURES, np.round(imp.importances_mean, 4).tolist(), strict=True))


def train(out_dir: Path, n: int = 7000, seed: int = SEED) -> dict:
    df = generate(n=n, seed=seed)
    x, y = df[FEATURES], df[TARGET].to_numpy()
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, stratify=y, random_state=seed
    )
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)

    # 1) Compare models with cross-validation on the training set only.
    cv_results = {}
    for name, model in candidate_models().items():
        scores = cross_validate(model, x_train, y_train, cv=cv,
                                scoring=["roc_auc", "average_precision"])  # fmt: skip
        cv_results[name] = {
            "roc_auc_mean": round(float(scores["test_roc_auc"].mean()), 4),
            "roc_auc_std": round(float(scores["test_roc_auc"].std()), 4),
            "avg_precision_mean": round(float(scores["test_average_precision"].mean()), 4),
        }
        print(f"{name:22s} CV ROC-AUC {cv_results[name]['roc_auc_mean']:.3f} "
              f"± {cv_results[name]['roc_auc_std']:.3f}  "
              f"AP {cv_results[name]['avg_precision_mean']:.3f}")  # fmt: skip
    best_name = max(
        (k for k in cv_results if k != "baseline_majority"),
        key=lambda k: cv_results[k]["avg_precision_mean"],
    )
    best = candidate_models()[best_name]

    # 2) Threshold from out-of-fold predictions (still training data only).
    oof = cross_val_predict(best, x_train, y_train, cv=cv, method="predict_proba")[:, 1]
    threshold = choose_threshold(y_train, oof)

    # 3) Refit on all training data, evaluate once on the untouched test set.
    best.fit(x_train, y_train)
    proba = best.predict_proba(x_test)[:, 1]
    pred = (proba >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_test, pred).ravel()
    test_metrics = {
        "roc_auc": round(float(roc_auc_score(y_test, proba)), 4),
        "avg_precision": round(float(average_precision_score(y_test, proba)), 4),
        "brier": round(float(brier_score_loss(y_test, proba)), 4),
        "precision": round(float(precision_score(y_test, pred)), 4),
        "recall": round(float(recall_score(y_test, pred)), 4),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        "expected_value_usd": round(expected_value(y_test, proba, threshold), 2),
        "contact_everyone_value_usd": round(expected_value(y_test, proba, 0.0), 2),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    importance = save_figures(y_test, proba, threshold, best, x_test, out_dir)
    metadata = {
        "model_name": best_name,
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
        "features": FEATURES,
        "threshold": threshold,
        "train_rows": len(x_train),
        "test_rows": len(x_test),
        "churn_rate": round(float(y.mean()), 4),
        "business_assumptions": {
            "customer_value": CUSTOMER_VALUE,
            "save_rate": SAVE_RATE,
            "offer_cost": OFFER_COST,
        },
        "cv_results": cv_results,
        "test_metrics": test_metrics,
        "permutation_importance": importance,
    }
    save_model(best, metadata, out_dir)
    pd.DataFrame(cv_results).T.to_csv(out_dir / "cv_results.csv")
    print(f"\nSelected {best_name} | threshold {threshold:.2f}")
    print(json.dumps(test_metrics, indent=2))
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    train(args.out_dir)


if __name__ == "__main__":
    main()
