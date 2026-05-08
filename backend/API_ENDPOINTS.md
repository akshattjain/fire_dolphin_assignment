# GitHub Repository Intelligence Tool — API Endpoints

**Base URL:** `http://localhost:8000/api`  
**Framework:** FastAPI (Python)  
**Content-Type:** `application/json` (all requests and responses)

---

## Health

### GET /api/health

Check that the server is running.

**Response `200 OK`**
```json
{
  "status": "ok"
}
```

---

## Ingest

### POST /api/ingest/repository

Submit a public GitHub repository URL for ingestion. If the repo is already ingested or in progress, returns the existing record. If a previous ingestion `FAILED`, it is automatically re-queued.

**Request Body**
```json
{
  "github_url": "https://github.com/owner/repo"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `github_url` | string | Yes | Full URL of the public GitHub repository |

**Response `202 Accepted`**
```json
{
  "repo_id": "uuid-string",
  "status": "PENDING",
  "message": "Repository ingestion queued successfully."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `repo_id` | string (UUID) | Unique identifier for the repository record |
| `status` | string | One of: `PENDING`, `CLONING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `message` | string | Human-readable status message |

---

### GET /api/ingest/repository/{repo_id}/status

Poll the ingestion progress for a previously submitted repository.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `repo_id` | string (UUID) | The repository ID returned from the ingest endpoint |

**Response `200 OK`**
```json
{
  "repo_id": "uuid-string",
  "github_url": "https://github.com/owner/repo",
  "owner": "owner",
  "name": "repo",
  "status": "COMPLETED",
  "total_files": 120,
  "processed_files": 120
}
```

| Field | Type | Description |
|-------|------|-------------|
| `repo_id` | string (UUID) | Repository identifier |
| `github_url` | string | Original GitHub URL submitted |
| `owner` | string \| null | Parsed GitHub owner/org name |
| `name` | string \| null | Parsed repository name |
| `status` | string | One of: `PENDING`, `CLONING`, `PROCESSING`, `COMPLETED`, `FAILED` |
| `total_files` | integer | Total number of files discovered |
| `processed_files` | integer | Number of files fully processed so far |

**Response `404 Not Found`**
```json
{
  "detail": "Repository not found."
}
```

---

## Chats

### POST /api/chats/sessions

Create a new chat session tied to an already-ingested repository. The repository must have `status: "COMPLETED"` before a session can be created.

**Request Body**
```json
{
  "repo_id": "uuid-string"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `repo_id` | string (UUID) | Yes | ID of a fully ingested repository |

**Response `201 Created`**
```json
{
  "session_id": "uuid-string",
  "repo_id": "uuid-string",
  "created_at": "2026-05-08T10:00:00Z"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `session_id` | string (UUID) | Unique identifier for the chat session |
| `repo_id` | string (UUID) | Repository this session is tied to |
| `created_at` | string (ISO 8601) | Session creation timestamp |

**Response `404 Not Found`**
```json
{
  "detail": "Repository not found."
}
```

**Response `400 Bad Request`**
```json
{
  "detail": "Repository is not ready yet (status: PROCESSING). Wait for ingestion to complete before starting a chat."
}
```

---

### GET /api/chats/sessions

List all chat sessions. Optionally filter by repository to support a resume-chat UX.

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_id` | string (UUID) | No | Filter sessions to a specific repository |

**Response `200 OK`**
```json
[
  {
    "id": "uuid-string",
    "repo_id": "uuid-string",
    "title": "How does the authentication flow work?",
    "created_at": "2026-05-08T10:00:00Z"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Session identifier |
| `repo_id` | string (UUID) | Repository this session belongs to |
| `title` | string \| null | Auto-generated from the first question (first 100 chars); null if no messages yet |
| `created_at` | string (ISO 8601) | Session creation timestamp |

---

### POST /api/chats/sessions/{session_id}/messages

Send a question to the RAG pipeline and receive an AI-generated answer with code citations.

**Pipeline:** Embeds the question → searches Qdrant for relevant code chunks → calls LLM with context and chat history → persists both turns → returns answer with citations.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | The chat session to send the message to |

**Request Body**
```json
{
  "question": "How does the authentication middleware work?"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `question` | string | Yes | Natural language question about the codebase |

**Response `200 OK`**
```json
{
  "message_id": "uuid-string",
  "answer": "The authentication middleware works by...",
  "citations": [
    {
      "file_path": "src/middleware/auth.py",
      "start_line": 12,
      "end_line": 45,
      "snippet": "def authenticate(request):\n    token = request.headers.get('Authorization')...",
      "chunk_type": "function",
      "name": "authenticate"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | string (UUID) | ID of the persisted assistant message |
| `answer` | string | LLM-generated answer to the question |
| `citations` | array | Up to 5 most relevant code chunks used as context |
| `citations[].file_path` | string | Relative path to the source file |
| `citations[].start_line` | integer | Starting line number of the chunk |
| `citations[].end_line` | integer | Ending line number of the chunk |
| `citations[].snippet` | string | Up to 400 characters of the source code |
| `citations[].chunk_type` | string | Type of code chunk (e.g. `function`, `class`, `module`) |
| `citations[].name` | string | Name of the function/class/symbol (empty string if not applicable) |

**Response `404 Not Found`**
```json
{
  "detail": "Session not found."
}
```

**Response `502 Bad Gateway`**
```json
{
  "detail": "Embedding service error: ..."
}
```
or
```json
{
  "detail": "LLM service error: ..."
}
```

---

### GET /api/chats/sessions/{session_id}/messages

Retrieve the full message history for a session (enables resume-chat functionality).

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string (UUID) | The chat session to retrieve messages for |

**Response `200 OK`**
```json
[
  {
    "id": "uuid-string",
    "role": "user",
    "content": "How does the authentication middleware work?",
    "created_at": "2026-05-08T10:01:00Z"
  },
  {
    "id": "uuid-string",
    "role": "assistant",
    "content": "The authentication middleware works by...",
    "created_at": "2026-05-08T10:01:05Z"
  }
]
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string (UUID) | Message identifier |
| `role` | string | Either `"user"` or `"assistant"` |
| `content` | string | Message text |
| `created_at` | string (ISO 8601) | Message creation timestamp |

**Response `404 Not Found`**
```json
{
  "detail": "Session not found."
}
```

---

## Status Enum Reference

| Status | Description |
|--------|-------------|
| `PENDING` | Repository queued, worker not yet started |
| `CLONING` | Worker is cloning the GitHub repo |
| `PROCESSING` | Worker is parsing and embedding files |
| `COMPLETED` | Ingestion finished; ready for queries |
| `FAILED` | Ingestion failed; re-submitting will retry |

---

## Typical Workflow

```
1. POST /api/ingest/repository          → get repo_id
2. GET  /api/ingest/repository/{id}/status  → poll until status = "COMPLETED"
3. POST /api/chats/sessions             → get session_id (pass repo_id)
4. POST /api/chats/sessions/{id}/messages  → ask questions, get answers + citations
5. GET  /api/chats/sessions/{id}/messages  → resume a previous conversation
```
