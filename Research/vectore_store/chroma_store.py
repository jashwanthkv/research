# vectorstore/chroma_store.py

import chromadb
from chromadb.config import Settings
from typing import List
from config import embeddings
# ------------------ CONFIG ------------------

COLLECTION_NAME = "paper_chunks"
collection = None

# Use in-memory DB (session scoped)# Make sure init_chroma() is defined correctly

def init_chroma():
    """
    Initialize or load the Chroma collection.
    Call once at app startup.
    """
    global collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )
    print(f"[OK] Collection initialized: {collection}")  # Debug

client = chromadb.Client(
    Settings(
        anonymized_telemetry=False
    )
)



def embed_text(text: str):
    return embeddings.embed_query(text)
# ------------------ INIT ------------------



# ------------------ RESET ------------------

def reset_chroma():
    """
    Clear all vectors (call when new fetch starts).
    """
    global collection
    client.delete_collection(COLLECTION_NAME)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )


# ------------------ ADD PAPER ------------------

def add_paper_chunks(paper_id: str, full_text: str, chunk_size=500, overlap=100):
    """
    Chunk full paper text, embed, and store in Chroma.
    """

    if not full_text.strip():
        return

    words = full_text.split()
    chunks = []

    start = 0
    idx = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append((idx, chunk))
        idx += 1
        start = end - overlap

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for idx, chunk in chunks:
        ids.append(f"{paper_id}::chunk_{idx}")
        documents.append(chunk)
        embeddings.append(embed_text(chunk))
        metadatas.append({"paper_id": paper_id})

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas
    )


# ------------------ RESOLVE ------------------

def resolve_papers(query: str, top_k_chunks=10, top_k_papers=3) -> List[str]:
    """
    Resolve relevant paper_ids using vector similarity.
    """

    if collection.count() == 0:
        return []

    query_embedding = embed_text(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k_chunks
    )

    paper_scores = {}

    for meta in results["metadatas"][0]:
        pid = meta["paper_id"]
        paper_scores[pid] = paper_scores.get(pid, 0) + 1

    # Sort papers by hit count
    ranked = sorted(paper_scores.items(), key=lambda x: x[1], reverse=True)

    return [pid for pid, _ in ranked[:top_k_papers]]
