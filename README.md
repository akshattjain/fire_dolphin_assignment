# GitHub Repository Intelligence Tool

> Ingest any public GitHub repository and ask natural language questions about its codebase — getting back precise answers with exact file paths, line numbers, and code snippets.

---

## Table of Contents

1. [Thought Process & Approach](#1-thought-process--approach)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Tech Stack](#3-tech-stack)
4. [Setup & Installation](#4-setup--installation)
5. [Usage Examples](#5-usage-examples)
6. [Limitations & Future Work](#6-limitations--future-work)

---

## 1. Thought Process & Approach

### First Understanding of the Problem

The main challenge was answering questions about code accurately without overwhelming the LLM with an entire repository. Since the assignment required precise outputs like file paths, line numbers, and code snippets, using summaries or compressed representations was not reliable. Another key challenge was scalability — the system needed to efficiently handle repositories of different sizes without overloading the HTTP layer or consuming excessive API resources.

### Approaches Considered

**Option A — Keyword / grep search + LLM summarisation**

Simple to implement. BM25 or a plain `grep` finds files containing the right tokens, then an LLM reads those files. The problem: natural language questions don't always share vocabulary with the code. Asking *"where is the login logic?"* returns nothing if the codebase calls it `authenticate_user`. Keyword search has no semantic understanding.

**Option B — Full-file embeddings**

Embed each file as a single vector, retrieve the top-k most relevant files, and pass them to the LLM. Better than keyword search, but a 500-line file embedded as one vector loses intra-file locality. If one function at line 42 answers the question, you get the whole 500 lines in context — noisy and expensive.

**Option C — Chunk-level embeddings (chosen)**

Split every file into overlapping, fixed-size chunks of source lines. Each chunk is embedded independently. At query time, retrieve only the chunks most semantically similar to the question. This keeps context tight and preserves exact line-number metadata from the moment the chunk is created.

I chose Option C because it directly satisfies the precision requirement: every retrieved chunk carries its `file_path`, `start_line`, and `end_line`.

### Key Design Decisions

**Chunking strategy — sliding window, not AST-first**

My first instinct was to use `tree-sitter` to parse Abstract Syntax Trees and extract named functions and classes as semantic chunks. This is theoretically superior because each chunk is a complete, meaningful unit. In practice it introduced three problems: (1) grammar packages are not uniformly available for all languages, (2) very large functions produce oversized chunks that do not embed well, and (3) configuration and edge-case handling adds complexity that can break silently. I pivoted to a sliding-window chunker with 50-line windows and 10-line overlap. This is language-agnostic, robust, predictable, and still captures local structure because adjacent context is preserved by the overlap. The overlap ensures that a code pattern spanning a chunk boundary still appears in at least one chunk.

**Single Qdrant collection, `repo_id` as namespace**

Rather than creating one Qdrant collection per repository (which would require dynamic collection management and explode under many repos), I use a single collection `code_chunks` and tag every point with a `repo_id` payload field. All searches include a `must` filter on `repo_id`. This is standard in production vector databases — the namespace is a metadata filter, not a structural boundary. It scales horizontally without schema changes.

**Asynchronous ingestion via RabbitMQ + Celery**

Cloning a repository and processing hundreds of files takes seconds to minutes. Blocking an HTTP request for that duration is unacceptable. The API immediately creates a database record, dispatches a Celery task to RabbitMQ, and returns the `repo_id`. The client polls `/status` until the status transitions to `COMPLETED`. This pattern (fire-and-forget + polling) is simple, observable, and resilient — the task can be retried automatically on failure.

**Dual SQLAlchemy engines**

FastAPI uses `asyncpg` (async) for non-blocking request handling. Celery workers are synchronous; running `asyncio.run()` inside a Celery task creates a fresh event loop per call, which fights with connection pooling. The cleaner solution is a dedicated `psycopg2`-backed synchronous session factory used only by worker code. The API and the worker never share sessions; they share only the database.

**Raw files in S3, chunks in Qdrant, metadata in Postgres**

Each storage layer holds exactly what it is good at: S3 stores arbitrary binary/text at low cost; Qdrant stores and searches dense vectors efficiently; Postgres stores structured metadata (file paths, line numbers, statuses, chat history) that needs relational queries and foreign-key integrity. This separation makes each layer independently replaceable.

**Chat history in Postgres, not in memory**

Storing conversation turns in the database means any client with the `session_id` can resume the conversation at any time. No server-side session state is required, and history survives server restarts. The last 10 turns are injected into each LLM call as a rolling window to bound token cost.

**React frontend**

The backend is a pure REST API, so I added a lightweight React + TypeScript frontend (Vite) to make the tool usable without curl. It has two views: a Home page to paste a GitHub URL and watch ingestion progress, and a Chat page with a markdown-rendering conversation interface that displays citations alongside answers.

### What Did Not Work

My initial implementation pointed `ingestion_service` at the `ast_service` (tree-sitter). While the AST parser worked for Python and Go in isolation, it failed silently for JavaScript/TypeScript because the `language_typescript` / `language_tsx` function signatures differ between tree-sitter-typescript versions. The result was that many files produced zero chunks — they were skipped entirely. Debugging this across five language grammars mid-assignment was not time-efficient. I stripped the AST layer and replaced it with the sliding-window chunker, which is uniform across all languages and never silently skips a file. The lesson: correctness and predictability beat cleverness when the stakes are a deadline.

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│              CLIENT  (React UI :5173  /  curl)                      │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │      FastAPI  :8000      │
                    │  (async, CORS enabled)  │
                    └──┬──────────────────┬───┘
                       │                  │
           ┌───────────▼──────┐  ┌────────▼───────────┐
           │  POST /ingest/   │  │   POST /chats/      │
           │  repository      │  │   sessions/{id}/    │
           │                  │  │   messages          │
           │  1. Write row    │  │                     │
           │     (PENDING)    │  │  1. Load history    │
           │  2. Enqueue task │  │     (Postgres)      │
           │  3. Return 202   │  │  2. Embed question  │
           └────────┬─────────┘  │     (OpenAI)        │
                    │            │  3. Search Qdrant   │
          ┌─────────▼──────┐     │  4. Build context   │
          │   RabbitMQ     │     │  5. GPT-4o-mini     │
          │   (broker)     │     │  6. Persist turns   │
          └─────────┬──────┘     │  7. Return answer + │
                    │            │     citations        │
          ┌─────────▼──────┐     └────────────────────┘
          │  Celery Worker  │
          │  (sync)         │
          │                 │
          │  ① Clone repo   │──────────────────► /tmp/repo_<id>/
          │    (GitPython)  │
          │                 │
          │  ② GitHub API   │──────────────────► stars, language,
          │    (PyGithub)   │                    description …
          │                 │
          │  ③ Walk files   │
          │    filter exts  │
          │                 │
          │  For each file: │
          │  ┌─────────────┐│
          │  │ S3 upload   ││──────────────────► s3://fire-dolphin/
          │  │ (boto3)     ││                    repos/{owner}/{repo}/
          │  ├─────────────┤│
          │  │ Slide-window ││
          │  │ chunker     ││  50 lines / 10 overlap
          │  │(chunk_svc)  ││
          │  ├─────────────┤│
          │  │ OpenAI      ││──────────────────► text-embedding-3-small
          │  │ embed_texts ││                    (batch, 1536-dim)
          │  ├─────────────┤│
          │  │ Qdrant      ││──────────────────► collection: code_chunks
          │  │ upsert      ││                    payload.repo_id = namespace
          │  └─────────────┘│
          │                 │
          │  ④ Write rows   │──────────────────► PostgreSQL
          │    CodeFile +   │                    code_files
          │    CodeChunk    │                    code_chunks
          │                 │
          │  ⑤ status =     │──────────────────► repositories.status
          │    COMPLETED    │                    = "COMPLETED"
          └─────────────────┘

──────────────────────── PostgreSQL tables ───────────────────────────
  repositories   id · github_url · owner · name · status · total_files
  code_files     id · repo_id · file_path · language · s3_key
  code_chunks    id · file_id · chunk_type · start_line · end_line
  chat_sessions  id · repo_id · title · created_at
  messages       id · session_id · role · content · created_at
```

---

## 3. Tech Stack

| Layer | Technology | Role |
|---|---|---|
| Frontend | React 19 + TypeScript + Vite | Chat UI with markdown-rendered citations |
| API | FastAPI (Python 3.12) | Async HTTP server |
| Task queue | Celery + RabbitMQ | Background ingestion |
| Database | PostgreSQL + SQLAlchemy 2 | Structured metadata & chat history |
| Vector store | Qdrant | Semantic chunk retrieval |
| Object store | AWS S3 (boto3) | Raw file storage |
| Embeddings | OpenAI `text-embedding-3-small` | 1536-dim dense vectors |
| LLM | OpenAI `gpt-4o-mini` | Natural language answers |
| Repo cloning | GitPython | Shallow clone (depth=1) |
| GitHub metadata | PyGithub | Stars, language, description |
| Chunker | Custom sliding-window | Language-agnostic, 50-line/10-overlap |

---

## 4. Setup & Installation

### Prerequisites

- Python 3.12+
- Node.js 18+ and npm
- Docker & Docker Compose
- An OpenAI API key
- AWS credentials with S3 read/write access (or a local MinIO instance)

---

### Backend

#### Step 1 — Clone the repository

```bash
git clone https://github.com/akshattjain/firedolphin_assignment.git
cd firedolphin_assignment/backend
```

#### Step 2 — Install Python dependencies

```bash
# Using uv (recommended)
pip install uv
uv sync


#### Step 3 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
# PostgreSQL
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fire_dolphin
DATABASE_SYNC_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/fire_dolphin

# Qdrant
QDRANT_URL=http://localhost:6333

# RabbitMQ
RABBITMQ_URL=amqp://guest:guest@localhost:5672//

# AWS S3
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1
S3_BUCKET_NAME=fire-dolphin

# OpenAI  ← required
OPENAI_API_KEY=sk-...
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_LLM_MODEL=gpt-4o-mini

# GitHub (optional — raises rate limit from 60 to 5000 req/hr)
GITHUB_TOKEN=ghp_...
```

#### Step 4 — Start infrastructure services

```bash
docker compose up -d
```

This starts PostgreSQL (port 5432), Qdrant (port 6333), and RabbitMQ (port 5672 / management UI at 15672).

```bash
docker compose ps   # all should show "healthy" or "running"
```

#### Step 5 — Create the S3 bucket

```bash
aws s3 mb s3://fire-dolphin --region us-east-1
```

Or create it in the AWS Console. The bucket name must match `S3_BUCKET_NAME` in your `.env`.
I did this and did not ran the command. I made bucket named `firedolphin`.

#### Step 6 — Start the FastAPI server

```bash
uv run main.py
```

The API is now live at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

#### Step 7 — Start the Celery worker (separate terminal)

```bash
celery -A src.services.queue_service.main worker --loglevel=info
```

You should see output confirming the worker is ready and the `ingest_repository` task is registered.

---

### Frontend

#### Step 8 — Install dependencies and start the dev server

```bash
cd ../frontend
npm install
npm run dev
```

The UI is now live at `http://localhost:5173`.

---

## 5. Usage Examples

The workflow has two stages: **ingest** a repository once, then **chat** about it. Both can be done through the React UI or via the REST API directly.

### Stage A — Ingest a repository

```bash
curl -X POST http://localhost:8000/api/ingest/repository \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/tiangolo/fastapi"}'
```

**Response (202 Accepted):**
```json
{
  "repo_id": "a3f7c021-84b2-4e91-bc3a-7d9e2f1a0c55",
  "status": "PENDING",
  "message": "Repository ingestion queued successfully."
}
```

Poll for progress:

```bash
curl http://localhost:8000/api/ingest/repository/a3f7c021-84b2-4e91-bc3a-7d9e2f1a0c55/status
```

**Response (when ready):**
```json
{
  "repo_id": "a3f7c021-84b2-4e91-bc3a-7d9e2f1a0c55",
  "github_url": "https://github.com/tiangolo/fastapi",
  "owner": "tiangolo",
  "name": "fastapi",
  "status": "COMPLETED",
  "total_files": 187,
  "processed_files": 187
}
```

### Stage B — Create a chat session

```bash
curl -X POST http://localhost:8000/api/chats/sessions \
  -H "Content-Type: application/json" \
  -d '{"repo_id": "a3f7c021-84b2-4e91-bc3a-7d9e2f1a0c55"}'
```

**Response:**
```json
{
  "session_id": "c91d4b2e-33a7-48f0-a1bc-9e2d0f7c3811",
  "repo_id": "a3f7c021-84b2-4e91-bc3a-7d9e2f1a0c55",
  "created_at": "2026-05-09T14:32:07.421Z"
}
```

---

### Query 1 — "Where is routing and path operation registration handled?"

```bash
curl -X POST \
  http://localhost:8000/api/chats/sessions/c91d4b2e-33a7-48f0-a1bc-9e2d0f7c3811/messages \
  -H "Content-Type: application/json" \
  -d '{"question": "Where is routing and path operation registration handled?"}'
```

**Response:**
```json
{
  "message_id": "d04a8f71-5c2e-4b90-a33e-1e2901c7f445",
  "answer": "Routing and path operation registration is handled in `fastapi/routing.py`. The `APIRouter` class collects route definitions, and the `add_api_route` method (lines 302–375) is invoked whenever you use a decorator like `@router.get(...)`. It wraps your handler in an `APIRoute` object and appends it to `self.routes`. The main `FastAPI` application in `fastapi/applications.py` holds a root `APIRouter` instance; calling `app.include_router(other_router)` merges the other router's routes into it.\n\nKey location: `fastapi/routing.py:302-375` — `APIRouter.add_api_route`.",
  "citations": [
    {
      "file_path": "fastapi/routing.py",
      "start_line": 302,
      "end_line": 351,
      "snippet": "def add_api_route(\n    self,\n    path: str,\n    endpoint: Callable[..., Any],\n    *,\n    response_model: Any = Default(None),\n    status_code: Optional[int] = None,\n    ..."
    },
    {
      "file_path": "fastapi/applications.py",
      "start_line": 1,
      "end_line": 50,
      "snippet": "from fastapi.routing import APIRouter\n\nclass FastAPI(Starlette):\n    def __init__(self, *, debug: bool = False, ...):\n        self.router: APIRouter = APIRouter(...)"
    }
  ]
}
```

---

### Query 2 — "Which file handles dependency injection and how does Depends work?"

```bash
curl -X POST \
  http://localhost:8000/api/chats/sessions/c91d4b2e-33a7-48f0-a1bc-9e2d0f7c3811/messages \
  -H "Content-Type: application/json" \
  -d '{"question": "Which file handles dependency injection and how does Depends work?"}'
```

**Response:**
```json
{
  "message_id": "e17b9a03-6d41-4c88-b55f-2f3012d8e556",
  "answer": "Dependency injection is split across two files.\n\n`fastapi/params.py` (lines 4–18) defines the `Depends` class — it is a simple dataclass holding a reference to the callable and a `use_cache` flag. There is no logic here; it is purely a marker.\n\nThe resolution logic lives in `fastapi/dependencies/utils.py`. When FastAPI handles a request it calls `solve_dependencies` (lines 445–600), which recursively resolves the dependency graph: it inspects each `Depends` annotation via `get_dependant`, calls each dependency function (or returns a cached result when `use_cache=True`), and injects the resolved values as keyword arguments into the endpoint.",
  "citations": [
    {
      "file_path": "fastapi/dependencies/utils.py",
      "start_line": 445,
      "end_line": 500,
      "snippet": "async def solve_dependencies(\n    *,\n    request: Union[Request, WebSocket],\n    dependant: Dependant,\n    body: Optional[Union[Dict[str, Any], FormData]] = None,\n    ...\n) -> Tuple[Dict[str, Any], List[ErrorWrapper], Optional[BackgroundTasks]]:"
    },
    {
      "file_path": "fastapi/params.py",
      "start_line": 4,
      "end_line": 18,
      "snippet": "class Depends:\n    def __init__(\n        self,\n        dependency: Optional[Callable[..., Any]] = None,\n        *,\n        use_cache: bool = True,\n    ) -> None:\n        self.dependency = dependency\n        self.use_cache = use_cache"
    }
  ]
}
```

---

### Query 3 — "Show me all API endpoints defined in this project"

```bash
curl -X POST \
  http://localhost:8000/api/chats/sessions/c91d4b2e-33a7-48f0-a1bc-9e2d0f7c3811/messages \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me all API endpoints defined in this project"}'
```

**Response:**
```json
{
  "message_id": "f28c0b14-7e52-4d99-c66a-3e4123e9f667",
  "answer": "Based on the retrieved code, FastAPI's own endpoints are defined in `fastapi/applications.py`. The framework registers three internal routes automatically:\n\n1. `GET /openapi.json` — returns the OpenAPI schema (lines 210–225)\n2. `GET /docs` — serves the Swagger UI (lines 226–240)\n3. `GET /redoc` — serves the ReDoc UI (lines 241–255)\n\nThese are added conditionally during `__init__` only when `openapi_url` and `docs_url` are not set to `None`.\n\nFor user-defined routes, FastAPI provides `@app.get`, `@app.post`, `@app.put`, `@app.delete`, and `@app.patch` decorators — all thin wrappers around `self.router.add_api_route`.",
  "citations": [
    {
      "file_path": "fastapi/applications.py",
      "start_line": 200,
      "end_line": 260,
      "snippet": "if self.openapi_url:\n    async def openapi() -> Response:\n        return JSONResponse(self.openapi())\n    self.add_route(\n        self.openapi_url,\n        openapi,\n        include_in_schema=False,\n    )\n    if self.docs_url:\n        ..."
    }
  ]
}
```

---

### API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/ingest/repository` | Submit a GitHub URL for ingestion |
| `GET` | `/api/ingest/repositories` | List all ingested repositories |
| `GET` | `/api/ingest/repository/{repo_id}/status` | Poll ingestion status & file progress |
| `POST` | `/api/chats/sessions` | Create a new chat session for a repo |
| `GET` | `/api/chats/sessions?repo_id=` | List sessions (optionally filter by repo) |
| `POST` | `/api/chats/sessions/{session_id}/messages` | Send a question, receive answer + citations |
| `GET` | `/api/chats/sessions/{session_id}/messages` | Retrieve full chat history |

Full interactive docs at `http://localhost:8000/docs` when the server is running.

---

## 6. Limitations & Future Work

### Current Limitations

**Chunking is not semantically aware**
The sliding-window chunker does not understand code structure. A 50-line window may cut a function in half or merge two unrelated functions. This reduces retrieval precision — the returned snippet may include irrelevant lines above or below the actual answer. An AST-based chunker that extracts complete function and class bodies would fix this for supported languages.

**No re-ingestion / incremental update**
Once a repository is marked `COMPLETED`, submitting the same URL returns the cached record. If the upstream repository is updated, the indexed data goes stale. There is no webhook listener, scheduled refresh, or diff-based update mechanism.

**Token cost scales with repository size**
Every code file is chunked and embedded through the OpenAI API. A large monorepo produces many API calls and non-trivial cost. No deduplication, local embedding model fallback, or incremental processing is implemented.

**Sequential per-file processing**
The Celery worker processes files one at a time within a single task. For large repositories this means ingestion can take several minutes. Dispatching per-file subtasks as a Celery `group` would enable true parallelism across multiple workers.

**No minified-file filter**
Files larger than 500 KB are skipped, but minified JavaScript (e.g. `bundle.min.js`) passes the size check and produces meaningless chunks that pollute the vector store.

**LLM can hallucinate on absent context**
When no relevant chunks are retrieved, GPT-4o-mini sometimes fabricates plausible-sounding file paths. The system prompt instructs the model to admit when it cannot find the answer, but LLMs do not always comply.

### Future Work

- **AST-based chunking** — Use `tree-sitter` for languages with stable grammars (Python, Go, Java) and fall back to the sliding window for others. Each chunk would be a complete, named definition with guaranteed semantic coherence.
- **Hybrid search** — Combine dense vector search (semantic similarity) with sparse BM25 keyword search using Qdrant's built-in hybrid search. This improves recall for exact identifier queries such as "find the `UserService` class".
- **Incremental ingestion** — Store the latest commit SHA per repository; on re-submission, only re-embed files that changed between the stored SHA and `HEAD`.
- **Parallel file processing** — Fan-out ingestion into a Celery `group` of per-file subtasks, with a `chord` callback that marks the repository `COMPLETED` once all subtasks finish.
- **GitHub App / webhook** — Automatically trigger re-ingestion on push events so the index stays current without manual polling.
- **Authentication** — JWT-based user accounts so chat history is private and sessions are scoped per user rather than per anonymous `session_id`.
- **Cost controls** — A local embedding model (e.g. `sentence-transformers/all-MiniLM-L6-v2` via Ollama) as an opt-in alternative to the OpenAI embedding API, reducing cost to zero for embedding at the price of slightly lower retrieval quality.
