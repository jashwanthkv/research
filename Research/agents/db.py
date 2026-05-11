from tools.tools import search_db_similarity, get_paper_details
from services.task_manager import add_task_log

def db(state):
    print("\n" + "="*70, flush=True)
    print("DATABASE RETRIEVAL AGENT RUNNING", flush=True)
    print("="*70, flush=True)

    query = state.get("userQuery", "")
    requested_k = state.get("max_results")
    
    print(f" Query: '{query}'", flush=True)
    print(f" Requesting {requested_k} papers from database", flush=True)

    matches = search_db_similarity(
        query,
        top_k=requested_k * 2,   # over-fetch
        search_field="abstract"
    )

    # confidence filter
    matches = [
        m for m in matches
        if m.get("score", 1.0) > 0.75
    ]

    paper_ids = [m["paper_id"] for m in matches[:requested_k]]

    papers = get_paper_details(paper_ids)

    print(f"\nRETRIEVED {len(papers)} papers from database", flush=True)
    for i, p in enumerate(papers, 1):
        print(f"   [{i}] {p.get('title', '')[:70]}", flush=True)
    
    add_task_log(state.get("task_id"), f"[DB] Retrieved {len(papers)} papers: {', '.join([p.get('title', '')[:50] for p in papers])}")
    print("="*70 + "\n", flush=True)

    return {
        "retrieved_papers": papers,
        "retrieval_attempted": True,
        "has_active_papers": len(papers) > 0,
        "active_paper_ids": paper_ids
    }

