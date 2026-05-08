"""
Celery task definitions for the ingestion pipeline.

Task flow
---------
POST /ingest/repository  (FastAPI, async)
    → creates Repository row (PENDING)
    → dispatches ingest_repository_task.delay(repo_id, github_url)
    → returns immediately

ingest_repository_task  (Celery worker, sync)
    1.  Clone repo to /tmp/repo_<repo_id>/
    2.  Fetch GitHub metadata
    3.  Update Repository row (PROCESSING)
    4.  For each code file → process_single_file → save CodeFile + CodeChunks
    5.  Update Repository row (COMPLETED | FAILED)
    6.  Clean up temp dir
"""

import logging
import traceback

from dotenv import load_dotenv

load_dotenv()

from src.config.postgres_config import sync_session_factory
from src.config.rabbitmq_config import celery_app
from src.services.git_service.main import cleanup_temp_dir, clone_repository, get_code_files
from src.services.github_service.main import fetch_repo_metadata
from src.services.ingestion_service.main import process_single_file
from src.services.qdrant_service.main import ensure_collection

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60, name="ingest_repository")
def ingest_repository_task(self, repo_id: str, github_url: str) -> None:
    """Main ingestion task executed asynchronously by the Celery worker."""
    session = sync_session_factory()
    try:
        # Import models inside task to avoid import-time side-effects in the worker
        from src.models.ingest.metadata import CodeChunk, CodeFile
        from src.models.ingest.repository import Repository

        repo: Repository | None = session.get(Repository, repo_id)
        if repo is None:
            logger.error("Repository %s not found in DB — aborting task", repo_id)
            return

        # ------------------------------------------------------------------ #
        # 1. Clone
        # ------------------------------------------------------------------ #
        repo.status = "CLONING"
        session.commit()

        try:
            temp_dir = clone_repository(github_url, repo_id)
        except Exception as exc:
            logger.error("Clone failed for %s: %s", github_url, exc)
            repo.status = "FAILED"
            session.commit()
            raise self.retry(exc=exc)

        # ------------------------------------------------------------------ #
        # 2. GitHub metadata
        # ------------------------------------------------------------------ #
        metadata = fetch_repo_metadata(github_url)
        repo.owner = metadata["owner"]
        repo.name = metadata["name"]
        repo.description = metadata["description"]
        repo.stars = metadata["stars"]
        repo.default_branch = metadata["default_branch"]
        repo.primary_language = metadata["primary_language"]

        # ------------------------------------------------------------------ #
        # 3. Discover files
        # ------------------------------------------------------------------ #
        code_files = get_code_files(temp_dir)
        repo.total_files = len(code_files)
        repo.status = "PROCESSING"
        session.commit()

        # Ensure Qdrant collection exists before writing any points
        ensure_collection()

        # ------------------------------------------------------------------ #
        # 4. Process each file
        # ------------------------------------------------------------------ #
        total = len(code_files)
        processed = 0
        for idx, file_info in enumerate(code_files):
            logger.info(
                "[INGEST] [%d/%d] starting: %s",
                idx + 1,
                total,
                file_info["file_path"],
            )
            try:
                result = process_single_file(
                    repo_id=repo_id,
                    file_info=file_info,
                    owner=metadata["owner"],
                    repo_name=metadata["name"],
                )
                if result is None:
                    continue

                # Persist CodeFile
                code_file = CodeFile(
                    repo_id=repo_id,
                    file_path=result["file_path"],
                    language=result["language"],
                    s3_key=result["s3_key"],
                    file_size=result["file_size"],
                )
                session.add(code_file)
                session.flush()  # get code_file.id before adding chunks

                # Persist CodeChunks
                for chunk_data in result["chunks"]:
                    session.add(
                        CodeChunk(
                            file_id=code_file.id,
                            chunk_type=chunk_data["chunk_type"],
                            name=chunk_data["name"],
                            start_line=chunk_data["start_line"],
                            end_line=chunk_data["end_line"],
                            qdrant_point_id=chunk_data["qdrant_point_id"],
                        )
                    )

                processed += 1
                repo.processed_files = processed
                session.commit()
                logger.info(
                    "[INGEST] [%d/%d] done: %s  (%d chunks)",
                    processed,
                    total,
                    result["file_path"],
                    len(result["chunks"]),
                )

            except Exception as exc:
                logger.warning(
                    "Failed to process %s: %s\n%s",
                    file_info["file_path"],
                    exc,
                    traceback.format_exc(),
                )
                session.rollback()
                # Re-attach repo after rollback
                repo = session.get(Repository, repo_id)

        # ------------------------------------------------------------------ #
        # 5. Mark completed
        # ------------------------------------------------------------------ #
        repo.status = "COMPLETED"
        session.commit()
        logger.info("Ingestion completed for repo %s (%d files)", repo_id, processed)

    except Exception as exc:
        logger.error("Ingestion task failed for repo %s: %s", repo_id, exc)
        try:
            from src.models.ingest.repository import Repository as Repo

            repo = session.get(Repo, repo_id)
            if repo:
                repo.status = "FAILED"
                session.commit()
        except Exception:
            pass
        raise

    finally:
        session.close()
        cleanup_temp_dir(repo_id)
