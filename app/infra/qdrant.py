from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from app.config import settings

client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

VECTOR_SIZE = 1536  # text-embedding-3-small dimension


def ensure_collection(name: str) -> None:
    """Create a Qdrant collection if it doesn't exist."""
    existing = [c.name for c in client.get_collections().collections]
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def upsert_points(collection: str, points: list[PointStruct]) -> None:
    """Insert or update points in a collection."""
    ensure_collection(collection)
    client.upsert(collection_name=collection, points=points)


def search_collection(
    collection: str,
    vector: list[float],
    limit: int = 10,
    score_threshold: float | None = None,
    filter_conditions: dict[str, str] | None = None,
) -> list:
    """Search a collection using query_points (qdrant-client v1.18+)."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    qdrant_filter = None
    if filter_conditions:
        must = []
        for key, value in filter_conditions.items():
            must.append(FieldCondition(key=key, match=MatchValue(value=value)))
        qdrant_filter = Filter(must=must)

    results = client.query_points(
        collection_name=collection,
        query=vector,
        query_filter=qdrant_filter,
        limit=limit,
        score_threshold=score_threshold,
        with_payload=True,
    )
    return results.points


def delete_collection(name: str) -> None:
    """Delete a collection if it exists."""
    existing = [c.name for c in client.get_collections().collections]
    if name in existing:
        client.delete_collection(collection_name=name)


def health_check() -> bool:
    """Check Qdrant connectivity."""
    try:
        client.get_collections()
        return True
    except Exception:
        return False
