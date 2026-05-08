import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.config.qdrant_config import QDRANT_API_KEY, QDRANT_URL

logger = logging.getLogger(__name__)

COLLECTION_NAME = "code_chunks"
VECTOR_SIZE = 1536  # OpenAI text-embedding-3-small


def get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def ensure_collection() -> None:
    """Create the Qdrant collection if it does not already exist."""
    client = get_client()
    existing = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        logger.info("Created Qdrant collection '%s'", COLLECTION_NAME)


def upsert_chunks(chunks: list[dict]) -> list[str]:
    """
    Upsert a list of chunk dicts into Qdrant.

    Each dict must contain: repo_id, file_path, language, chunk_type, name,
    start_line, end_line, content, embedding.
    Returns the list of assigned point UUIDs.
    """
    client = get_client()
    points: list[PointStruct] = []
    point_ids: list[str] = []

    for chunk in chunks:
        pid = str(uuid.uuid4())
        point_ids.append(pid)
        points.append(
            PointStruct(
                id=pid,
                vector=chunk["embedding"],
                payload={
                    "repo_id": chunk["repo_id"],
                    "file_path": chunk["file_path"],
                    "language": chunk["language"],
                    "chunk_type": chunk["chunk_type"],
                    "name": chunk.get("name"),
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "content": chunk["content"],
                },
            )
        )

    if points:
        client.upsert(collection_name=COLLECTION_NAME, points=points)

    return point_ids


def search_chunks(query_vector: list[float], repo_id: str, limit: int = 10) -> list[dict]:
    """
    Semantic search within a specific repo's chunks.
    repo_id acts as the namespace filter inside the shared collection.
    """
    client = get_client()
    response = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(
            must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
        ),
        limit=limit,
        with_payload=True,
    )
    return [{"score": hit.score, "payload": hit.payload} for hit in response.points]


def delete_repo_chunks(repo_id: str) -> None:
    """Delete all Qdrant points belonging to a repository."""
    client = get_client()
    client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=Filter(
            must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
        ),
    )
