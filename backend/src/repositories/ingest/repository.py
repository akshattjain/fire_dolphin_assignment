from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.ingest.repository import Repository


async def create_repository(session: AsyncSession, github_url: str) -> Repository:
    repo = Repository(github_url=github_url)
    session.add(repo)
    await session.commit()
    await session.refresh(repo)
    return repo


async def get_repository(session: AsyncSession, repo_id: str) -> Repository | None:
    return await session.get(Repository, repo_id)


async def get_repository_by_url(session: AsyncSession, github_url: str) -> Repository | None:
    result = await session.execute(
        select(Repository).where(Repository.github_url == github_url)
    )
    return result.scalar_one_or_none()


async def get_all_repositories(session: AsyncSession) -> list[Repository]:
    result = await session.execute(
        select(Repository).order_by(Repository.created_at.desc())
    )
    return list(result.scalars().all())
