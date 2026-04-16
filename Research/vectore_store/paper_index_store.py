# vectorstore/paper_index_store.py

import chromadb
from chromadb.config import Settings
from config import embeddings
from datetime import datetime
from typing import List, Dict, Optional

COLLECTION_NAME = "paper_index"

client = chromadb.Client(
    Settings(anonymized_telemetry=False)
)

collection = None


def init_paper_index():
    global collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print("✅ Paper-index Chroma initialized")


def add_paper_to_index(
    paper_id: str,
    title: str,
    abstract: str,
    year: int,
    url: str = ""          # ← NEW: store link
):
    if not title:
        return

    text = f"{title}\n\n{abstract or ''}"
    embedding = embeddings.embed_query(text)

    collection.add(
        ids=[paper_id],
        embeddings=[embedding],
        documents=[text],
        metadatas=[{
            "paper_id":  paper_id,          # ← NEW
            "title":     title,             # ← NEW
            "url":       url or "",         # ← NEW
            "year":      year or "",
            "stored_at": datetime.utcnow().isoformat()
        }]
    )


def get_paper_from_index(paper_id: str) -> Optional[Dict]:
    """
    Fetch metadata for a single paper by paper_id.
    Returns dict with title, year, url — or None if not found.
    """
    try:
        result = collection.get(ids=[paper_id], include=["metadatas"])
        metas = result.get("metadatas", [])
        if metas:
            return metas[0]
    except Exception as e:
        print(f"[paper_index] get_paper_from_index error: {e}")
    return None


def query_paper_index(
    query: str,
    top_k: int = 5
) -> List[Dict]:
    """
    Return metadata for decision agent (year + count).
    """
    if collection.count() == 0:
        return []

    query_embedding = embeddings.embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k
    )

    return results.get("metadatas", [[]])[0]