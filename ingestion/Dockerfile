FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/srv/.venv \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/
COPY ingestion/pyproject.toml ingestion/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package ingestion --no-install-workspace

COPY core/ core/
COPY ingestion/ ingestion/
COPY evals/ evals/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package ingestion

ENV PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv/ingestion

ENTRYPOINT ["python", "-m", "app.cli"]
CMD ["scan"]
