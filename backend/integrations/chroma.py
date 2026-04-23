"""
ChromaDB integration - vector retrieval for context-aware generation.
"""

from config import CHROMA_DIR


def get_chroma_client():
    """Get or create ChromaDB client."""
    try:
        import chromadb
        return chromadb.PersistentClient(path=str(CHROMA_DIR))
    except ImportError:
        return None


def is_chroma_available() -> bool:
    return get_chroma_client() is not None


def get_or_create_collection(name: str = "clawseries"):
    """Get or create a collection for character/asset embeddings."""
    client = get_chroma_client()
    if not client:
        return None
    return client.get_or_create_collection(name=name)


def add_documents(ids: list[str], documents: list[str], metadatas: list[dict] | None = None):
    """Add documents to the default collection."""
    collection = get_or_create_collection()
    if not collection:
        return
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas or [{}] * len(ids))


def query_similar(query_text: str, n_results: int = 5) -> list[dict]:
    """Query for similar documents."""
    collection = get_or_create_collection()
    if not collection:
        return []
    results = collection.query(query_texts=[query_text], n_results=n_results)
    hits = []
    for i, doc in enumerate(results["documents"][0]):
        hits.append({
            "id": results["ids"][0][i],
            "document": doc,
            "distance": results["distances"][0][i] if "distances" in results else None,
            "metadata": results["metadatas"][0][i] if "metadatas" in results else {},
        })
    return hits
