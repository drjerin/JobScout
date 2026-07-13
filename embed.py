"""Local embeddings via sentence-transformers (bge-small-en-v1.5).

Runs entirely on CPU and works offline after the first model download.
The resume never leaves the machine.
"""
from __future__ import annotations

import numpy as np

import logs

_log = logs.get("scout.embed")
_MODEL_NAME = "BAAI/bge-small-en-v1.5"
_model = None


def _load():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise SystemExit(
                "sentence-transformers is not installed.\n"
                "Run:  pip install -r requirements.txt"
            ) from e
        _log.info("loading model %s (first run downloads ~130 MB)...", _MODEL_NAME)
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed(texts):
    """Return an ``(n, d)`` float32 array of L2-normalized embeddings.

    Accepts a single string or a list of strings.
    """
    model = _load()
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    vecs = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
        batch_size=32,
    )
    return vecs.astype(np.float32)


def cosine(a, b):
    """Cosine similarity between one vector ``a`` (d,) and matrix ``b`` (n, d).

    Both are assumed L2-normalized, so this is just ``b @ a``. Returns ``(n,)``.
    """
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    if b.ndim == 1:
        b = b[None, :]
    return b @ a
