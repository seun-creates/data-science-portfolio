"""Save and load model artifacts with integrity checks.

1. only ever load model files this project produced itself (never downloaded ones)
2. verify the file's SHA-256 checksum against the metadata
"""

from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import joblib

MODEL_FILE = "model.joblib"
META_FILE = "metadata.json"


class ModelIntegrityError(RuntimeError):
    """The model file does not match its recorded checksum."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_model(model: Any, metadata: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / MODEL_FILE
    joblib.dump(model, model_path)
    meta = {**metadata, "model_file": MODEL_FILE, "sha256": sha256_of(model_path)}
    (out_dir / META_FILE).write_text(json.dumps(meta, indent=2))
    return model_path


def load_metadata(model_dir: Path) -> dict:
    return json.loads((model_dir / META_FILE).read_text())


def load_verified_model(model_dir: Path) -> tuple[Any, dict]:
    """Load the model only if its checksum matches the metadata."""
    meta = load_metadata(model_dir)
    model_path = model_dir / MODEL_FILE
    actual = sha256_of(model_path)
    # compare_digest: constant-time comparison, a good habit for any secret-ish value
    if not hmac.compare_digest(actual, str(meta.get("sha256", ""))):
        raise ModelIntegrityError(f"checksum mismatch for {model_path}; refusing to load")
    return joblib.load(model_path), meta
