import json
import re
from config import llm

DEFAULT_PAPER_COUNT = 1
MAX_PAPER_COUNT     = 10

SYSTEM_PROMPT = """You are an intent classifier for a research assistant.

You will receive:
- The current topic already analyzed (if any)
- The user's new query

Classify into ONE of these intents:

════════════════════════════════════════
"new_fetch"
════════════════════════════════════════
User EXPLICITLY wants NEW papers fetched.
The key signal is: user is asking to FIND, GET, FETCH, SHOW, or RESEARCH papers.

Examples → new_fetch:
  "find 3 papers on black holes"
  "get me papers about climate change"
  "research transformer architecture"
  "show papers on YOLO"
  "fetch articles on deep learning"
  "explain 4 papers on social media"
  "i want papers on quantum computing"
  "give me research on LSTM"
  "search for papers on attention mechanism"
  "papers on reinforcement learning"

════════════════════════════════════════
"continuation"
════════════════════════════════════════
User is asking a follow-up or doubt about the ALREADY analyzed papers/topic.
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
User asks a general concept/knowledge question.
NOT asking for papers. Just wants an explanation of something.

Examples → general_question:
  "how does GPU work?"
  "what is backpropagation?"
  "explain the transformer architecture"
  "what is YOLO?"
  "how does LSTM differ from RNN?"
  "what is gradient descent?"
  "explain attention mechanism"
  "what is overfitting?"

════════════════════════════════════════
"end"
════════════════════════════════════════
  "thanks", "bye", "done", "stop", "exit", "that's all"

════════════════════════════════════════
DECISION RULE:
- If user says "papers on X" / "research on X" / "find/get/fetch/show papers" → new_fetch
- If user asks about something already discussed → continuation  
- If user asks what/how/why about a concept (no paper request) → general_question
- When in doubt between continuation and general_question → pick general_question

Return ONLY valid JSON:
{
  "intent": "new_fetch" | "continuation" | "general_question" | "end",
  "paper_count": <integer or null>,
  "reason": "<one short sentence explaining your choice>"
}
"""


def decision(state):
    print("---DECISION AGENT---")

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

        print(f"[Decision] intent={llm_intent} | reason={reason}")
        print(f"[Decision] paper_count={llm_count}")

    except Exception as e:
        print(f"[Decision] LLM parse failed: {e}")
        llm_intent = "continuation" if has_active_papers else "general_question"

    requested_count = llm_count if isinstance(llm_count, int) else DEFAULT_PAPER_COUNT
    requested_count = min(requested_count, MAX_PAPER_COUNT)
    print(f"[Decision] Final paper count: {requested_count}")


    if llm_intent == "end":
        return {"next_step": "end", "answer_mode": "analysis"}


    if llm_intent == "new_fetch":
        print("[Decision] New fetch → fetch agent")
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


    if llm_intent == "continuation" and has_active_papers and active_paper_ids:
        print("[Decision] Continuation → continuous_explanation")
        return {
            "next_step":        "continuous_explanation",
            "answer_mode":      "analysis",
            "active_paper_ids": active_paper_ids,
        }


    if llm_intent in ("general_question", "continuation"):
        print("[Decision] General/concept question → continuous_explanation (Tavily ready)")
        return {
            "next_step":        "continuous_explanation",
            "answer_mode":      "analysis",
            "active_paper_ids": active_paper_ids,
        }

    if retrieval_attempted and not has_active_papers:
        print("[Decision] DB empty → forcing fetch")
        return {
            "next_step":     "fetch",
            "fetch_query":   user_query,
            "answer_mode":   "analysis",
            "max_results":   requested_count,
            "current_topic": user_query,
        }

    if has_active_papers and active_paper_ids and not analysis_done:
        print("[Decision] Papers exist, not analysed → analyse")
        return {
            "next_step":         "analyse",
            "answer_mode":       "analysis",
            "active_paper_ids":  active_paper_ids,
            "has_active_papers": True,
            "max_results":       requested_count,
        }


    print("[Decision] Default → retrieve")
    return {
        "next_step":   "retrieve",
        "answer_mode": "analysis",
        "max_results": requested_count,
    }