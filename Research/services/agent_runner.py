from vectore_store.chroma_store import reset_chroma
from services.task_manager import complete_task, update_step, get_task
from services.agent_wrapper import wrap_agent

from agents.decision import decision
from agents.db import db
from agents.fetch import fetch
from agents.analyse import analyse
from agents.explain import explain
from agents.continuous_explanation import continuous_explanation

from graph.graph import State, build_graph

import json
import uuid
import threading

from services.redis import redis_client

SESSION_TTL = 1800  # 30 minutes

# ──────────────────────────────────────────────────────────
# IN-PROCESS SESSION STORE
# Lives in RAM for the lifetime of the server process.
# Chroma is also in-RAM so they stay in sync automatically.
# ──────────────────────────────────────────────────────────
_SESSION_STORE: dict = {}
_SESSION_LOCK = threading.Lock()


def load_state(session_id: str) -> dict | None:
    # 1. In-process store (fastest, guaranteed in sync with Chroma)
    with _SESSION_LOCK:
        state = _SESSION_STORE.get(session_id)
        if state:
            return json.loads(json.dumps(state))  # deep copy

    # 2. Redis fallback
    try:
        raw = redis_client.get(session_id)
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    return None


def save_state(session_id: str, state: dict):
    try:
        safe = json.loads(json.dumps(state, default=str))
    except Exception:
        safe = state

    with _SESSION_LOCK:
        _SESSION_STORE[session_id] = safe

    try:
        redis_client.setex(session_id, SESSION_TTL, json.dumps(safe, default=str))
    except Exception as e:
        print(f"[Session] Redis save failed (non-critical): {e}")


def run_task(task_id: str, query: str, session_id: str | None = None, year_from: int | None = None, year_to: int | None = None):
    try:
        if not session_id:
            session_id = str(uuid.uuid4())
            print(f"  No session_id from frontend → new: {session_id}")
        else:
            print(f"🔑 Session: {session_id}")

        state = load_state(session_id)

        if not state:
            print("🆕 New session → initializing state")
            reset_chroma()

            state = {
                "task_id":             task_id,
                "userQuery":           query,
                "goal":                "research the latest papers on the topic and provide an analysis",
                "active_paper_ids":    [],
                "resolved_paper_ids":  None,
                "fetch_query":         None,
                "max_results":         0,
                "retrieval_attempted": False,
                "has_active_papers":   False,
                "analysis_done":       False,
                "next_step":           "retrieve",
                "answer_mode":         "analysis",
                "analysis":            None,
                "explanation":         "",
                "year_from":           year_from,  # ← add year filter
                "year_to":             year_to      # ← add year filter
            }
        else:
            print("♻️  Existing session → resuming")
            print(f"    has_active_papers={state.get('has_active_papers')} | "
                  f"analysis_done={state.get('analysis_done')} | "
                  f"papers={state.get('active_paper_ids', [])}")

            state["task_id"]           = task_id
            state["userQuery"]         = query
            state["analysis_done"]     = state.get("analysis_done", False)
            state["has_active_papers"] = state.get("has_active_papers", False)
            state["active_paper_ids"]  = state.get("active_paper_ids", [])
            state["year_from"]         = year_from  # ← update year filter
            state["year_to"]           = year_to    # ← update year filter

        wrapped_agents = {
            "decision":wrap_agent(decision,"decision",task_id),
            "db":wrap_agent(db,"retrieve",task_id),
            "fetch":wrap_agent(fetch,"fetch",task_id),
            "analyse":wrap_agent(analyse,"analyse",task_id),
            "explain":wrap_agent(explain,"explain",task_id),
            "continuous_explanation": wrap_agent(continuous_explanation, "continuous_explanation", task_id),
        }

        graph       = build_graph(wrapped_agents)
        final_state = graph.invoke(state)

        save_state(session_id, final_state)
        print(f"[Session] Saved → analysis_done={final_state.get('analysis_done')} | "
              f"has_active_papers={final_state.get('has_active_papers')}")

        task = get_task(task_id)
        for step in task["progress"]:
            if step["state"] == "pending":
                update_step(task_id, step["step"], "skipped")

        complete_task(
            task_id=task_id,
            mode=final_state.get("answer_mode", "analysis"),
            papers=final_state.get("fetched_papers") or final_state.get("retrieved_papers"),
            result={
                "analysis":    final_state.get("analysis"),
                "explanation": final_state.get("explanation"),
                "session_id":  session_id,   # ← returned to frontend every time
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        update_step(task_id, "explain", "error")
        complete_task(
            task_id=task_id,
            mode="analysis",
            papers=[],
            result={"error": str(e), "session_id": session_id}
        )