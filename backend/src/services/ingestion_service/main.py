"""
Helper functions called by the Celery ingestion task.
Kept separate so logic can be unit-tested independently of Celery.
"""

import logging
from concurrent.futures import ThreadPoolExecutor

from src.services.chunk_service.main import parse_file
from src.services.llm_service.main import embed_texts
from src.services.qdrant_service.main import upsert_chunks
from src.services.s3_service.main import build_s3_key, upload_file

logger = logging.getLogger(__name__)

MAX_CHUNKS_PER_FILE = 100




def process_single_file(
    repo_id: str,
    file_info: dict,
    owner: str,
    repo_name: str,
) -> dict | None:
    """
    Per-file pipeline — S3 upload is fire-and-forget (non-blocking):

      1. Read file from disk
      2. Queue S3 upload in background   ← fires immediately, does NOT block
      3. Parse into chunks               ← runs in parallel with step 2
      4. Batch-embed all chunks via OpenAI
      5. Upsert into Qdrant

    Returns a result dict for the Celery task to write DB records,
    or None if the file could not be read or embedded.
    """
    file_path: str = file_info["file_path"]
    language: str = file_info["language"]
    abs_path: str = file_info["abs_path"]
    file_size: int = file_info["file_size"]

    # 1. Read
    try:
        with open(abs_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
    except OSError as exc:
        logger.warning("[READ]   cannot read %s: %s", file_path, exc)
        return None

    if not content.strip():
        return None

    # 2. S3 upload synchronously (safe inside Celery worker)
    s3_key = build_s3_key(owner, repo_name, file_path)
    logger.info("[S3]     uploading → %s", file_path)
    try:
        upload_file(content, s3_key)
        logger.info("[S3]     ✓ uploaded  %s", file_path)
    except Exception as exc:
        logger.warning("[S3]     ✗ failed    %s: %s", file_path, exc)

    # 3. Chunking — starts immediately (runs in parallel with S3 above)
    logger.info("[CHUNK]  chunking %s  (%s)", file_path, language)
    raw_chunks = parse_file(content, language)
    raw_chunks = raw_chunks[:MAX_CHUNKS_PER_FILE]
    logger.info("[CHUNK]  %d chunk(s) extracted from %s", len(raw_chunks), file_path)

    if not raw_chunks:
        return {
            "file_path": file_path,
            "language": language,
            "s3_key": s3_key,
            "file_size": file_size,
            "chunks": [],
        }

    # 4. Embed
    texts = [
        f"{c.chunk_type} {c.name or ''} in {file_path}:\n{c.content}"
        for c in raw_chunks
    ]
    logger.info("[EMBED]  embedding %d chunk(s) for %s", len(texts), file_path)
    try:
        embeddings = embed_texts(texts)
        logger.info("[EMBED]  ✓ done for %s", file_path)
    except Exception as exc:
        logger.warning("[EMBED]  ✗ failed for %s: %s", file_path, exc)
        return None

    # 5. Qdrant upsert
    qdrant_payloads = [
        {
            "repo_id": repo_id,
            "file_path": file_path,
            "language": language,
            "chunk_type": c.chunk_type,
            "name": c.name,
            "start_line": c.start_line,
            "end_line": c.end_line,
            "content": c.content,
            "embedding": emb,
        }
        for c, emb in zip(raw_chunks, embeddings)
    ]
    logger.info("[QDRANT] upserting %d vector(s) for %s", len(qdrant_payloads), file_path)
    try:
        point_ids = upsert_chunks(qdrant_payloads)
        logger.info("[QDRANT] ✓ upserted %d vector(s) for %s", len(point_ids), file_path)
    except Exception as exc:
        logger.warning("[QDRANT] ✗ upsert failed for %s: %s", file_path, exc)
        point_ids = [None] * len(raw_chunks)

    return {
        "file_path": file_path,
        "language": language,
        "s3_key": s3_key,
        "file_size": file_size,
        "chunks": [
            {
                "chunk_type": c.chunk_type,
                "name": c.name,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "qdrant_point_id": pid,
            }
            for c, pid in zip(raw_chunks, point_ids)
        ],
    }
