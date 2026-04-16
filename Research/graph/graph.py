import sys
import os
from tkinter import Image
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from langgraph.graph import StateGraph, START, END
from typing import TypedDict, List, Any, Literal, Optional

from agents.decision import decision
from agents.db import db
from agents.fetch import fetch
from agents.analyse import analyse
from agents.explain import explain
from agents.continuous_explanation import continuous_explanation


class State(TypedDict):
    userQuery:            str
    goal:                 str

    active_paper_ids:     List[str]
    resolved_paper_ids:   List[str] | None

    fetch_query:          Optional[str]
    current_topic:        Optional[str]   # ← what topic is currently loaded
    max_results:          int
    retrieval_attempted:  bool
    has_active_papers:    bool
    analysis_done:        bool

    next_step:   Literal["retrieve", "fetch", "analyse", "continuous_explanation", "end"]
    answer_mode: Literal["reference", "analysis"]

    analysis:    Any
    explanation: str


def build_graph(agents=None):
    graph = StateGraph(State)

    _decision = agents["decision"]if agents else decision
    _db= agents["db"]if agents else db
    _fetch= agents["fetch"]if agents else fetch
    _analyse= agents["analyse"]if agents else analyse
    _explain= agents["explain"]if agents else explain
    _continuous = agents.get("continuous_explanation", continuous_explanation) if agents else continuous_explanation

    graph.add_node("decision",_decision)
    graph.add_node("db",_db)
    graph.add_node("fetch",_fetch)
    graph.add_node("analyse",_analyse)
    graph.add_node("explain",_explain)
    graph.add_node("continuous_explanation", _continuous)

    graph.add_edge(START, "decision")

    graph.add_conditional_edges(
        "decision",
        lambda state: state["next_step"],
        {
            "retrieve":"db",
            "fetch":"fetch",
            "analyse":"analyse",
            "continuous_explanation": "continuous_explanation",
            "end":END,
        }
    )

    graph.add_edge("db", "decision")

    graph.add_conditional_edges(
        "fetch",
        lambda state: state["answer_mode"],
        {
            "analysis":"analyse",
            "reference": END,
        }
    )

    graph.add_edge("analyse","explain")
    graph.add_edge("explain",END)
    graph.add_edge("continuous_explanation", END)

    return graph.compile()


