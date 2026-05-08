from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres_config import async_session_factory
from src.repositories.chats.chats import (
    create_session,
    get_session,
    list_sessions,
    update_session_title,
)
from src.repositories.chats.messages import create_message, list_messages
from src.repositories.ingest.repository import get_repository
from src.schemas.chats import (
    CitationSchema,
    CreateSessionRequest,
    CreateSessionResponse,
    MessageSchema,
    SendMessageRequest,
    SendMessageResponse,
    SessionSchema,
)
from src.services.chat_service.main import answer_question
from src.services.llm_service.main import embed_text
from src.services.qdrant_service.main import search_chunks

router = APIRouter(prefix="/chats", tags=["chats"])


async def get_db():
    async with async_session_factory() as session:
        yield session


@router.post("/sessions", response_model=CreateSessionResponse, status_code=201)
async def create_chat_session(
    request: CreateSessionRequest,
    session: AsyncSession = Depends(get_db),
):
    """Create a new chat session for an already-ingested repository."""
    repo = await get_repository(session, request.repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found.")
    if repo.status != "COMPLETED":
        raise HTTPException(
            status_code=400,
            detail=f"Repository is not ready yet (status: {repo.status}). "
            "Wait for ingestion to complete before starting a chat.",
        )

    chat_session = await create_session(session, request.repo_id)
    return CreateSessionResponse(
        session_id=chat_session.id,
        repo_id=chat_session.repo_id,
        created_at=chat_session.created_at,
    )


@router.get("/sessions", response_model=list[SessionSchema])
async def list_chat_sessions(
    repo_id: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """List all sessions, optionally filtered by repo_id (for resume-chat UX)."""
    sessions = await list_sessions(session, repo_id)
    return [
        SessionSchema(
            id=s.id,
            repo_id=s.repo_id,
            title=s.title,
            created_at=s.created_at,
        )
        for s in sessions
    ]


@router.post(
    "/sessions/{session_id}/messages",
    response_model=SendMessageResponse,
    status_code=200,
)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Send a question and receive a RAG-powered answer with code citations.

    Pipeline:
      1. Load chat history from Postgres
      2. Embed question with OpenAI text-embedding-3-small
      3. Search Qdrant (filtered by repo_id)
      4. Build context from top-k chunks
      5. Call GPT-4o-mini with history + context
      6. Persist both turns to Postgres
      7. Return answer + citations
    """
    chat_session = await get_session(session, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    # 1. History
    history_rows = await list_messages(session, session_id)
    history = [{"role": m.role, "content": m.content} for m in history_rows]

    # 2. Embed query
    try:
        query_vector = embed_text(request.question)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Embedding service error: {exc}")

    # 3. Search
    search_results = search_chunks(query_vector, chat_session.repo_id, limit=10)

    # 4 & 5. Generate answer
    try:
        answer = answer_question(request.question, search_results, history)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM service error: {exc}")

    # 6. Persist turns
    await create_message(session, session_id, "user", request.question)
    assistant_msg = await create_message(session, session_id, "assistant", answer)

    # Set session title from the first question
    if not chat_session.title:
        await update_session_title(session, session_id, request.question[:100])

    # 7. Build citations from top-5 results
    citations = [
        CitationSchema(
            file_path=r["payload"]["file_path"],
            start_line=r["payload"]["start_line"],
            end_line=r["payload"]["end_line"],
            snippet=r["payload"]["content"][:400],
            chunk_type=r["payload"]["chunk_type"],
            name=r["payload"].get("name") or "",
        )
        for r in search_results[:5]
    ]

    return SendMessageResponse(
        message_id=assistant_msg.id,
        answer=answer,
        citations=citations,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[MessageSchema])
async def get_session_messages(
    session_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Return the full message history for a session (enables resume-chat)."""
    chat_session = await get_session(session, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = await list_messages(session, session_id)
    return [
        MessageSchema(
            id=m.id,
            role=m.role,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]
