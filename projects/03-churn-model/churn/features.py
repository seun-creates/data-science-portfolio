"""Feature definitions and preprocessing, shared by training and the API."""

from __future__ import annotations

from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

TARGET = "churned"
NUMERIC = [
    "tenure_months", "monthly_charges", "total_charges", "support_tickets_90d", "num_products",
]  # fmt: skip
BINARY = ["senior_citizen", "paperless_billing"]
CATEGORICAL = ["contract", "internet_service", "payment_method"]
FEATURES = NUMERIC + BINARY + CATEGORICAL


def build_preprocessor() -> ColumnTransformer:
    """Imputation + scaling + one-hot encoding.

    Everything is fitted inside the model pipeline, on training folds only, so no
    statistic from validation or test data can leak into training.
    """
    numeric = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())])
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            # handle_unknown="ignore": a category never seen in training won't crash scoring
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        [
            ("num", numeric, NUMERIC),
            ("bin", "passthrough", BINARY),
            ("cat", categorical, CATEGORICAL),
        ]
    )
