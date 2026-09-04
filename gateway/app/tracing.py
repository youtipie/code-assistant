"""OpenTelemetry export to a local Phoenix instance.

All the OTel lives here rather than in agent: `openinference` instruments
LangChain through its callback system, so the graph needs no knowledge of it.
Exporting is best-effort -- a trace backend that is down must not cost an
answer, so setup failures are logged and swallowed.
"""

from __future__ import annotations

import logging

from opentelemetry import trace

from .config import settings

log = logging.getLogger(__name__)

# Fetched before setup_tracing() registers anything: the OTel API returns a
# proxy that switches over when a global provider appears and stays a no-op if
# none does, which is what lets ws/turn.py open a span unconditionally.
tracer = trace.get_tracer("gateway.turn")

_provider = None


def setup_tracing() -> None:
    global _provider
    if not settings.tracing_enabled:
        log.info("tracing disabled")
        return
    if _provider is not None:  # --reload re-runs lifespan
        return
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from phoenix.otel import register

        _provider = register(
            endpoint=f"{settings.phoenix_collector_endpoint.rstrip('/')}/v1/traces",
            project_name=settings.tracing_project,
            # LangChain is instrumented explicitly below; auto_instrument
            # would also load every other openinference package it can find
            auto_instrument=False,
            batch=True,
            # the proxy tracer above resolves through the *global* provider
            set_global_tracer_provider=True,
            verbose=False,
        )
        LangChainInstrumentor().instrument(tracer_provider=_provider)
        log.info("tracing to %s", settings.phoenix_collector_endpoint)
    except Exception:
        _provider = None
        log.warning("tracing setup failed; continuing without it", exc_info=True)


def shutdown_tracing() -> None:
    """Flush the batch span processor, or the last turn before a restart is
    lost."""
    global _provider
    if _provider is None:
        return
    try:
        _provider.shutdown()
    except Exception:
        log.warning("tracing shutdown failed", exc_info=True)
    finally:
        _provider = None
