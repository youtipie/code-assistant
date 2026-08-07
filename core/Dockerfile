FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/srv/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package core --no-install-workspace

COPY core/ core/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package core

ENV PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv/core

CMD ["alembic", "upgrade", "head"]
