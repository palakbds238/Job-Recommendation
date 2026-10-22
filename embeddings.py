"""
embeddings.py — OPTIONAL semantic embeddings (sentence-transformers)

The recommender works without this module: if `sentence-transformers` is not
installed (it needs PyTorch, ~800 MB) or the model cannot be downloaded, the
app logs one line and falls back to TF-IDF + skill matching.

Enable:   pip install -r requirements-ml.txt
Control:  USE_EMBEDDINGS=auto (default) | 1 (require, error if missing) | 0 (off)
          EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2 (default)
"""
import logging
import os

import numpy as np

log = logging.getLogger("embeddings")
MODEL_NAME = os.environ.get("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_encoder = None          # callable: list[str] -> np.ndarray (n, d), L2-normalised
_tried = False
_name = None


def set_encoder(fn, name="custom"):
    """Inject an encoder (used by tests, or to plug in another model/API)."""
    global _encoder, _tried, _name
    _encoder, _tried, _name = fn, True, name


def _load():
    global _encoder, _tried, _name
    if _tried:
        return
    _tried = True
    mode = os.environ.get("USE_EMBEDDINGS", "auto").lower()
    if mode in ("0", "off", "false"):
        log.info("Embeddings disabled (USE_EMBEDDINGS=0).")
        return
    try:
        from sentence_transformers import SentenceTransformer
        st = SentenceTransformer(MODEL_NAME)

        def enc(texts):
            v = st.encode(list(texts), normalize_embeddings=True,
                          show_progress_bar=False)
            return np.asarray(v, dtype=np.float32)

        _encoder, _name = enc, MODEL_NAME
        log.info("Embeddings enabled: %s", MODEL_NAME)
    except Exception as e:  # noqa: BLE001
        if mode in ("1", "on", "true"):
            raise
        log.warning("Embeddings unavailable (%s: %s) — using TF-IDF + skills only.",
                    type(e).__name__, str(e)[:120])


def available() -> bool:
    _load()
    return _encoder is not None


def model_name():
    _load()
    return _name


def encode(texts):
    _load()
    if _encoder is None:
        raise RuntimeError("embeddings not available")
    return _encoder(texts)
