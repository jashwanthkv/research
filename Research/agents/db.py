from tools.tools import search_db_similarity, get_paper_details

def db(state):
    print("---RETRIEVE AGENT (DB)---")

    query = state.get("userQuery", "")
    requested_k = state.get("max_results")

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

    print(f"Retrieved {len(papers)} papers from DB.")

    return {
        "retrieved_papers": papers,
        "retrieval_attempted": True,
        "has_active_papers": len(papers) > 0
    }
