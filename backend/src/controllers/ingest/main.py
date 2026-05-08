from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.config.postgres_config import async_session_factory
from src.repositories.ingest.repository import (
    create_repository,
    get_all_repositories,
    get_repository,
    get_repository_by_url,
)
from src.schemas.ingest import (
    IngestRepositoryRequest,
    IngestRepositoryResponse,
    RepositoryStatusResponse,
)
from src.services.queue_service.main import ingest_repository_task

router = APIRouter(prefix="/ingest", tags=["ingest"])


async def get_db():
    async with async_session_factory() as session:
        yield session


@router.post("/repository", response_model=IngestRepositoryResponse, status_code=202)
async def ingest_repository(
    request: IngestRepositoryRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Submit a GitHub URL for ingestion.

    If the repository has already been ingested or is in progress, returns the
    existing record rather than re-queuing. To force re-ingestion, delete the
    existing record first.
    """
    existing = await get_repository_by_url(session, request.github_url)

    if existing:
        if existing.status == "COMPLETED":
            return IngestRepositoryResponse(
                repo_id=existing.id,
                status=existing.status,
                message="Repository already ingested — ready for queries.",
            )
        if existing.status in ("PENDING", "CLONING", "PROCESSING"):
            return IngestRepositoryResponse(
                repo_id=existing.id,
                status=existing.status,
                message="Ingestion already in progress.",
            )
        # FAILED — allow retry by falling through

    if existing and existing.status == "FAILED":
        repo = existing
        repo.status = "PENDING"
        await session.commit()
    else:
        repo = await create_repository(session, request.github_url)

    # Dispatch async Celery task; API returns immediately
    ingest_repository_task.delay(repo.id, request.github_url)

    return IngestRepositoryResponse(
        repo_id=repo.id,
        status="PENDING",
        message="Repository ingestion queued successfully.",
    )


@router.get("/repository/{repo_id}/status", response_model=RepositoryStatusResponse)
async def get_repository_status(
    repo_id: str,
    session: AsyncSession = Depends(get_db),
):
    """Poll ingestion progress for a repository."""
    repo = await get_repository(session, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found.")

    return RepositoryStatusResponse(
        repo_id=repo.id,
        github_url=repo.github_url,
        owner=repo.owner,
        name=repo.name,
        status=repo.status,
        total_files=repo.total_files,
        processed_files=repo.processed_files,
    )


@router.get("/repositories", response_model=list[RepositoryStatusResponse])
async def list_repositories(
    session: AsyncSession = Depends(get_db),
):
    """List all repositories."""
    repos = await get_all_repositories(session)
    return [
        RepositoryStatusResponse(
            repo_id=repo.id,
            github_url=repo.github_url,
            owner=repo.owner,
            name=repo.name,
            status=repo.status,
            total_files=repo.total_files,
            processed_files=repo.processed_files,
        )
        for repo in repos
    ]
