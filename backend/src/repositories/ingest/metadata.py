from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ingest.metadata import CodeChunk, CodeFile


async def get_files_for_repo(session: AsyncSession, repo_id: str) -> list[CodeFile]:
    result = await session.execute(
        select(CodeFile).where(CodeFile.repo_id == repo_id)
    )
    return list(result.scalars().all())


async def get_chunks_for_file(session: AsyncSession, file_id: str) -> list[CodeChunk]:
    result = await session.execute(
        select(CodeChunk).where(CodeChunk.file_id == file_id)
    )
    return list(result.scalars().all())
