FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/srv/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/
COPY agent/pyproject.toml agent/
COPY gateway/pyproject.toml gateway/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package gateway --no-install-workspace

COPY core/ core/
COPY agent/ agent/
COPY gateway/ gateway/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package gateway

ENV PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv/gateway

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
