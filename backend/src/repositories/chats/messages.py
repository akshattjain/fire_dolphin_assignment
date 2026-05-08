from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chats.messages import Message


async def create_message(
    session: AsyncSession, session_id: str, role: str, content: str
) -> Message:
    message = Message(session_id=session_id, role=role, content=content)
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return message


async def list_messages(session: AsyncSession, session_id: str) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return list(result.scalars().all())
