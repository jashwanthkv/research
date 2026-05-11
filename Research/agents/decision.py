import json
import re
from config import llm
from services.task_manager import add_task_log

DEFAULT_PAPER_COUNT = 1
MAX_PAPER_COUNT     = 10

SYSTEM_PROMPT = """You are an intent classifier for a research assistant.

You will receive:
- The current topic already analyzed (if any)
- The user's new query

Classify into ONE of these intents:

════════════════════════════════════════
"new_topic"
════════════════════════════════════════
User wants to explore a new research topic, find papers, or research a subject.
Even if they just provide a topic name (e.g. "LSTM" or "climate change"), assume they want papers on it unless they specifically ask a "what is/how does" question.

Examples → new_topic:
  "find 3 papers on black holes"
  "LSTM"
  "Recent advances in machine learning for NLP"
  "research transformer architecture"
  "show papers on YOLO"
  "fetch articles on deep learning"
  "give me research on LSTM"
  "search for papers on attention mechanism"
  "climate change impacts"

════════════════════════════════════════
"continuation"
════════════════════════════════════════
User is asking a follow-up about the ALREADY analyzed papers/topic.
No new papers needed — answer from existing knowledge.

Examples → continuation:
  "explain more about paper 2"
  "what is the methodology they used?"
  "compare the two papers"
  "summarize what we discussed"
  "what did they find about accuracy?"
  "tell me more about the results"
  "what are the limitations of these papers?"

════════════════════════════════════════
"general_question"
════════════════════════════════════════
User asks a specific factual or conceptual question NOT requiring paper retrieval.

Examples → general_question:
  "how does GPU work?"
  "what is backpropagation?"
  "what is the transformer architecture?"

════════════════════════════════════════
"end"
════════════════════════════════════════
  "thanks", "bye", "done", "stop", "exit", "that's all"

════════════════════════════════════════
DECISION RULE:
- If user provides a topic phrase or asks for papers → new_topic
- If user asks about something already discussed → continuation  
- If user asks a specific concept question (what/how/why) → general_question
- When in doubt between continuation and general_question → pick general_question

Return ONLY valid JSON:
{
  "intent": "new_topic" | "continuation" | "general_question" | "end",
  "paper_count": <integer or null>,
  "reason": "<one short sentence explaining your choice>"
}
"""


def decision(state):
    print("\n" + "="*70, flush=True)
    print("DECISION AGENT RUNNING", flush=True)
    print("="*70, flush=True)

    user_query          = state.get("userQuery", "")
    has_active_papers   = state.get("has_active_papers", False)
    analysis_done       = state.get("analysis_done", False)
    retrieval_attempted = state.get("retrieval_attempted", False)
    active_paper_ids    = state.get("active_paper_ids", [])

    current_topic = state.get("current_topic", "")
    if not current_topic and has_active_papers:
        current_topic = state.get("fetch_query", "")

    has_papers_context = (
        f"Current analyzed topic: '{current_topic}'"
        if (has_active_papers and current_topic)
        else "No papers have been analyzed yet."
    )

    llm_input = f"{has_papers_context}\n\nUser query: {user_query}"


    llm_intent = None
    llm_count  = None

    try:
        response = llm.invoke([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": llm_input}
        ])

        raw = response.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()

        parsed     = json.loads(raw)
        llm_intent = parsed.get("intent")
        llm_count  = parsed.get("paper_count")
        reason     = parsed.get("reason", "")

        print(f"[Decision] ✓ LLM Decision: intent='{llm_intent}' | reason={reason}", flush=True)
        print(f"[Decision] Requested papers: {llm_count}", flush=True)

    except Exception as e:
        print(f"[Decision] LLM parse failed: {e}", flush=True)
        llm_intent = "continuation" if has_active_papers else "new_topic"
        print(f"[Decision] ⚠ Fallback intent: {llm_intent}", flush=True)

    requested_count = llm_count if isinstance(llm_count, int) else DEFAULT_PAPER_COUNT
    requested_count = min(requested_count, MAX_PAPER_COUNT)
    print(f"[Decision] Final paper count: {requested_count}", flush=True)
    
    add_task_log(state.get("task_id"), f"[Decision] Intent: {llm_intent}, Requested Papers: {requested_count}")


    if llm_intent == "end":
        print(f"\nDECISION MADE: END_CONVERSATION", flush=True)
        print("="*70 + "\n", flush=True)
        return {"next_step": "end", "answer_mode": "analysis"}


    if llm_intent in ("continuation", "general_question"):
        print(f"\nDECISION MADE: {llm_intent.upper()}", flush=True)
        print(f"   → Answering from {len(active_paper_ids)} existing paper(s)", flush=True)
        print("="*70 + "\n", flush=True)
        return {
            "next_step":        "continuous_explanation",
            "answer_mode":      "analysis",
            "active_paper_ids": active_paper_ids,
        }


    if llm_intent in ("new_topic", "new_fetch"):
        if not retrieval_attempted:
            print(f"\nDECISION MADE: RETRIEVE_FROM_DB", flush=True)
            print(f"   → Fetching {requested_count} papers on: '{user_query}'", flush=True)
            print("="*70 + "\n", flush=True)
            return {
                "next_step":   "retrieve",
                "answer_mode": "analysis",
                "max_results": requested_count,
                "fetch_query": user_query,
                "current_topic": user_query,
            }
            
        if retrieval_attempted and not has_active_papers:
            print(f"\nDECISION MADE: FETCH_FROM_WEB", flush=True)
            print(f"   → DB empty, fetching {requested_count} papers from web", flush=True)
            print("="*70 + "\n", flush=True)
            return {
                "next_step":         "fetch",
                "fetch_query":       user_query,
                "answer_mode":       "analysis",
                "max_results":       requested_count,
                "current_topic":     user_query,
                "has_active_papers": False,
                "analysis_done":     False,
                "active_paper_ids":  [],
            }
            
        if has_active_papers and not analysis_done:
            print(f"\nDECISION MADE: ANALYZE_PAPERS", flush=True)
            print(f"   → Analyzing {len(active_paper_ids)} fetched paper(s)", flush=True)
            print("="*70 + "\n", flush=True)
            return {
                "next_step":         "analyse",
                "answer_mode":       "analysis",
                "active_paper_ids":  active_paper_ids,
                "has_active_papers": True,
                "max_results":       requested_count,
            }

    print("\nDECISION MADE: DEFAULT_RETRIEVE", flush=True)
    print(f"   → Fetching {requested_count} papers", flush=True)
    print("="*70 + "\n", flush=True)
    return {
        "next_step":   "retrieve",
        "answer_mode": "analysis",
        "max_results": requested_count,
        "active_paper_ids":  active_paper_ids,
        "has_active_papers": True,
        "max_results":requested_count,
    }

    print("[Decision] Default → retrieve")
    return {
        "next_step":   "retrieve",
        "answer_mode": "analysis",
        "max_results": requested_count,
    }