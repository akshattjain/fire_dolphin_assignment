from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chats.chats import ChatSession


async def create_session(session: AsyncSession, repo_id: str) -> ChatSession:
    chat_session = ChatSession(repo_id=repo_id)
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return chat_session


async def get_session(session: AsyncSession, session_id: str) -> ChatSession | None:
    return await session.get(ChatSession, session_id)


async def list_sessions(session: AsyncSession, repo_id: str | None = None) -> list[ChatSession]:
    query = select(ChatSession)
    if repo_id:
        query = query.where(ChatSession.repo_id == repo_id)
    query = query.order_by(ChatSession.created_at.desc())
    result = await session.execute(query)
    return list(result.scalars().all())


async def update_session_title(session: AsyncSession, session_id: str, title: str) -> None:
    chat_session = await session.get(ChatSession, session_id)
    if chat_session:
        chat_session.title = title
        await session.commit()
