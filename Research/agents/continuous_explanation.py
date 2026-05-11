from typing import Dict, Any, List
from config import llm
import vectore_store.chroma_store as chroma_store  # module import only
from tavily import TavilyClient

MAX_CHUNKS        = 10
MAX_CONTEXT_CHARS = 5000

tavily_search = TavilyClient(api_key="")

SYSTEM_PROMPT = """You are a research paper explainer helping a user understand content from analyzed papers.

You are given:
- The user's follow-up question
- Relevant chunks from previously analyzed research papers

Rules:
- Answer using ONLY the provided context when it's sufficient
- Be clear, concise, and technically accurate
- If the context does not contain enough information, respond with exactly: INSUFFICIENT_CONTEXT
- Do NOT introduce new papers or fabricate information
"""

FALLBACK_SYSTEM_PROMPT = """You are a precise technical explainer.
Answer the question using the provided external information.
Be concise and accurate. Cite sources when possible.
"""


def get_chunks_for_papers(paper_ids: List[str], query: str) -> List[str]:
    """Retrieve top relevant chunks from Chroma for the given paper_ids."""

    col = chroma_store.collection          # read at call-time, not import-time

    if not paper_ids or col is None:       # ← None check before .count()
        print("[Continuation] Chroma collection is None or no paper_ids")
        return []

    if col.count() == 0:
        print("[Continuation] Chroma collection is empty")
        return []

    try:
        query_embedding = chroma_store.embed_text(query)

        where_filter = (
            {"paper_id": paper_ids[0]}
            if len(paper_ids) == 1
            else {"paper_id": {"$in": paper_ids}}
        )

        results = col.query(
            query_embeddings=[query_embedding],
            n_results=min(MAX_CHUNKS, col.count()),
            where=where_filter
        )

        return results.get("documents", [[]])[0]

    except Exception as e:
        print(f"[Continuation] Chroma query error: {e}")

        # Fallback: query without paper_id filter
        try:
            col = chroma_store.collection
            if col is None:
                return []
            results = col.query(
                query_embeddings=[chroma_store.embed_text(query)],
                n_results=min(MAX_CHUNKS, col.count())
            )
            return results.get("documents", [[]])[0]
        except Exception as e2:
            print(f"[Continuation] Chroma fallback also failed: {e2}")
            return []


def is_insufficient(answer: str) -> bool:
    return (
        "INSUFFICIENT_CONTEXT" in answer
        or len(answer.strip()) < 40
        or answer.lower().startswith("i don't know")
        or answer.lower().startswith("i cannot")
    )


def format_tavily_results(response: Dict[str, Any]) -> str:
    snippets = []
    for r in response.get("results", []):
        title   = r.get("title", "")
        content = r.get("content", "")
        if content:
            snippets.append(f"**{title}**\n{content}")
    return "\n\n".join(snippets)


def continuous_explanation(state: Dict[str, Any]) -> Dict[str, Any]:
    print("\n" + "="*70)
    print("CONTINUOUS EXPLANATION AGENT RUNNING")
    print("="*70)

    user_query = state["userQuery"]
    paper_ids  = state.get("active_paper_ids", [])

    print(f" Query: '{user_query[:60]}'")
    print(f" Papers: {paper_ids}")

    # ── 1. Retrieve paper chunks from Chroma ──────────
    chunks  = get_chunks_for_papers(paper_ids, user_query)
    context = "\n\n---\n\n".join(chunks)[:MAX_CONTEXT_CHARS]

    print(f"Retrieved {len(chunks)} chunks from papers")

    # ── 2. Primary answer from paper context ──────────
    answer = ""
    if context.strip():
        response = llm.invoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Context from papers:\n{context}\n\nQuestion:\n{user_query}"}
        ])
        answer = response.content.strip()
        print(f"Generated answer from paper context ({len(answer)} chars)")

    # ── 3. Tavily fallback if context insufficient ─────
    if not context.strip() or is_insufficient(answer):
        print("Insufficient paper context → using web search")

        try:
            raw_external = tavily_search.search(user_query, max_results=4)
            external     = format_tavily_results(raw_external)

            response = llm.invoke([
                {"role": "system", "content": FALLBACK_SYSTEM_PROMPT},
                {"role": "user",   "content": f"External information:\n{external}\n\nQuestion:\n{user_query}"}
            ])
            answer = response.content.strip()
            print(f"Generated answer from web search ({len(answer)} chars)")

        except Exception as e:
            print(f"Web search failed: {e}")
            answer = "Sorry, I could not find enough information to answer your question."

    print("="*70 + "\n")
    return {"explanation": answer}