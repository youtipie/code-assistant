from __future__ import annotations

import logging
from collections.abc import Iterable

from .settings import core_settings

log = logging.getLogger(__name__)

MODEL_NAME = core_settings.embedding_model
CACHE_DIR = core_settings.embedding_cache
DIM = 384

_model = None


def model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding

        log.info("loading %s (first run downloads the model)", MODEL_NAME)
        _model = TextEmbedding(model_name=MODEL_NAME, cache_dir=CACHE_DIR)
        log.info("embedding model ready")
    return _model


def embed_passages(texts: Iterable[str], batch_size: int = 64) -> list[list[float]]:
    return [v.tolist() for v in model().embed(texts, batch_size=batch_size)]


def embed_query(text: str) -> list[float]:
    return next(iter(model().query_embed([text]))).tolist()
