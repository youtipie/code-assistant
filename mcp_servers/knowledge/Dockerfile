FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/srv/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /srv

COPY pyproject.toml uv.lock ./
COPY core/pyproject.toml core/
COPY mcp_servers/knowledge/pyproject.toml mcp_servers/knowledge/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package knowledge-mcp --no-install-workspace

COPY core/ core/
COPY mcp_servers/knowledge/ mcp_servers/knowledge/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package knowledge-mcp

ENV PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv/mcp_servers/knowledge

EXPOSE 8080
CMD ["python", "-m", "app.server"]
