# AI Engineering Assistant

An internal assistant that answers questions about a codebase and its
documentation. It retrieves from a vector index, calls tools over the Model
Context Protocol, and streams answers over WebSocket with citations that link
back to the exact line they came from.

Configured out of the box against [Saleor](https://github.com/saleor/saleor)
and its documentation repository.

```
you> Which service is responsible for invoice generation?

  → search_code(invoice generation)
    · saleor/plugins/webhook/plugin.py:1282
    · saleor/webhook/payloads.py:456
  → read_file(saleor/plugins/webhook/plugin.py :: invoice_request)

Saleor does not generate invoices itself. It requests one from an external
app via the INVOICE_REQUEST webhook (saleor/plugins/webhook/plugin.py:1282)…
```

## Features

- **Hybrid retrieval** — dense vectors, full-text search and an any-term
  branch, fused with Reciprocal Rank Fusion over pgvector
- **MCP tools** — a local `knowledge` server plus GitHub's official remote
  server, discovered at runtime
- **Streaming chat** — WebSocket with live tool calls, mid-turn cancellation
  and multi-session history
- **Scoped by design** — a classifier gate answers "who is Joe Biden?" with a
  refusal before the agent runs; only questions about the corpus get a turn
- **Verifiable citations** — every claim links to a file and line at the exact
  indexed commit
- **PR review and issue triage** — reads a diff or an issue and answers in chat
- **Local embeddings** — ONNX on CPU, no API calls during ingestion
- **Retrieval eval** — 171 questions scored with `ranx`: `hit_rate@{1,3,5,10}`
  and MRR with a 95% interval, listing every question that fell outside the
  top 5

## Architecture

```
Browser / CLI ──WebSocket──► FastAPI gateway ──► LangGraph agent
                                   │                   │
                                   │                   ├── OpenAI
                                   │                   └── Postgres checkpointer
                                   │
                                   └── MCP client ──┬── knowledge server
                                                    │   (pgvector search)
                                                    └── GitHub MCP server
```

| Service | Purpose | Port |
|---|---|---|
| `web` | React client behind nginx | 3000 |
| `gateway` | WebSocket + REST API, agent runtime | 8000 |
| `knowledge` | MCP server for code and doc retrieval | 8080 |
| `phoenix` | Local LLM trace UI and OTLP collector | 6006 |
| `postgres` | Sessions, documents, chunks, checkpoints, traces | 5433 |
| `migrate` | Runs migrations, then exits | — |
| `ingest` | One-shot corpus loader (profile `tools`) | — |

## Requirements

- Docker and Docker Compose
- An OpenAI API key
- ~4 GB RAM available to Docker
- Optional: a GitHub personal access token (no scopes needed for public repos)

## Quickstart

```bash
cp .env.example .env        # add OPENAI_API_KEY, optionally GITHUB_TOKEN
docker compose up -d
```

Load the corpus (~7 minutes; downloads a 130 MB embedding model on first run):

```bash
docker compose run --build --rm ingest load     # clone and store documents
docker compose run --rm ingest chunk            # chunk and embed
```

Open <http://localhost:3000>, or use the CLI:

```bash
uv run clients/cli.py
```

Traces are at <http://localhost:6006>: every model call with its prompt and
response, tokens, cost and latency, grouped into one session per conversation.
Each answer in the web client also carries a footer with the same numbers for
that turn. Set `TRACING_ENABLED=false` to run without it.

## Usage

### Web client

Ask a question and watch the trace: each tool call appears as it runs, with its
arguments, duration and retrieved sources. Citations link to GitHub at the
commit the index was built from. `Copy transcript` yields the whole turn —
question, tool calls, arguments, results, answer — as plain text.

### CLI

```bash
uv run clients/cli.py
```

`/new` starts a conversation, `/session` prints the id, `/quit` exits, Ctrl-C
cancels a response mid-stream.

### Ingestion and evaluation

```bash
docker compose run --rm ingest scan                    # summarise, write nothing
docker compose run --rm ingest load                    # store documents
docker compose run --rm ingest chunk                   # chunk and embed
docker compose run --rm ingest chunk --force           # re-chunk everything
docker compose run --rm ingest search "how do refunds work"
docker compose run --rm ingest eval                    # hit_rate@k and MRR
docker compose run --rm ingest eval --verbose          # every question, not just misses
docker compose run --rm ingest eval --limit 20         # score deeper than the default 10
docker compose run --rm ingest eval --questions /srv/evals/my_set.yaml
```

### Scope

The assistant answers about the indexed corpus and nothing else. Every question
is classified first, and one that has no connection to the codebase — a recipe,
a public figure, a bubble sort in Rust — is refused before the agent runs, so it
costs no tools and leaves nothing in the conversation for the next question to
be read against. The rule is stated twice on purpose: the gate enforces it, and
the system prompt states it again for anything that gets past. Ties go to
answering — a wrongly refused question looks broken, and the agent still says
"I could not find this in the indexed corpus" on its own.

```bash
uv run evals/scope.py            # 24 cases: on-topic, follow-ups, off-topic
uv run evals/scope.py --verbose  # every case, not just the failures
```

Set `SCOPE_GUARD_ENABLED=false` to measure the agent without it.

### Example questions

```
What is the deployment architecture?
How does a checkout become an order?
What fields does the Checkout model have?
When was complete_checkout.py last changed, and by which PR?     (needs GITHUB_TOKEN)
Make a code review of PR #19506                                  (needs GITHUB_TOKEN)
Is issue #17234 still valid given the current code?              (needs GITHUB_TOKEN)
```

## Configuration

Everything lives in `.env`. See `.env.example` for the full list.

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required |
| `OPENAI_MODEL` | `gpt-4.1` | Chat model |
| `OPENAI_USE_RESPONSES_API` | `true` | Required for reasoning models with tools |
| `OPENAI_REASONING_EFFORT` | — | `minimal`…`high`, or `none` |
| `GITHUB_TOKEN` | — | Enables the GitHub MCP server; skipped if empty |
| `CORPUS_REPOS` | `saleor/saleor=saleor/,saleor/saleor-docs=docs/` | Repo per path prefix |
| `CORPUS_NAME` | `Saleor` | What the assistant says it covers, in the scope gate's prompt and its refusal |
| `SCOPE_GUARD_ENABLED` | `true` | Refuse off-topic questions before the agent runs |
| `SCOPE_MODEL` | `gpt-4.1-mini` | Classifier for the scope gate; small and non-reasoning |
| `MAX_STEPS` | `12` | Tool hops per turn |
| `TRACING_ENABLED` | `true` | Export traces to Phoenix |
| `PHOENIX_COLLECTOR_ENDPOINT` | `http://phoenix:6006` | Where the gateway sends spans |
| `MODEL_PRICES` | — | `model=input/cached/output[/cache_write]` USD per 1M tokens, comma-separated; overrides the built-in table. An unpriced model shows a dash instead of a guess |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Local embedding model |
| `MCP_CONFIG` | `agent/mcp_servers.json` (absolute path, resolved relative to `agent/src/agent/config.py`) | MCP server declarations |

MCP servers are declared in `agent/mcp_servers.json`. `${VAR}` is substituted
from the environment, and `requires_env` skips a server whose credential is
absent.

### Indexing a different repository

Edit `SOURCES` in `ingestion/app/sources.py`, set `CORPUS_REPOS` and
`CORPUS_NAME` to match, adjust the first line of `SYSTEM_PROMPT`, then re-run
`ingest load` and `ingest chunk`.

## Project structure

```
core/                shared package: models, migrations, retrieval, embeddings
agent/               LangGraph orchestration, prompts, MCP tool policy
gateway/             FastAPI: WebSocket, REST, persistence
mcp_servers/
  knowledge/         MCP server exposing search_docs, search_code, outline, read_file
ingestion/           clone → chunk → embed → load, plus search and eval CLIs
web/                 React + TypeScript client
clients/cli.py       terminal client
evals/questions.yaml 171 retrieval questions with expected paths
evals/scope_cases.yaml + scope.py   scope-gate eval set and runner
```

## Development

A `uv` workspace with one lockfile for every Python service.

```bash
uv sync                                   # install everything
docker compose up postgres knowledge -d   # dependencies only
cd gateway && uv run uvicorn app.main:app --reload
```

Web client with hot reload (proxies `/api` and `/chat` to port 8000):

```bash
cd web && npm install && npm run dev      # http://localhost:5173
```

Adding a dependency:

```bash
uv add <package> --package gateway && uv lock
```

Regenerating the client's API types after changing a Pydantic response model:

```bash
cd web && npm run generate:api     # needs the gateway running on :8000
```

Regenerating the socket event contract after changing an event in
`core/events.py` or `gateway/app/protocol.py` (no running server needed):

```bash
cd web && npm run generate:events
```

Linting and type checks:

```bash
uv run ruff check .
cd web && npm run typecheck
```