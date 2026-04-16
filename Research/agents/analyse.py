import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field

from config import llm, llm_extract, llm_synth, llm_trends
from tools.tools import get_paper_chunks_by_paper_id, get_connection
from vectore_store.paper_index_store import get_paper_from_index


# ──────────────────────────────────────────────────────────
# PROMPTS
# ──────────────────────────────────────────────────────────

CHUNK_EXTRACT_PROMPT = """
You extract factual information from a research paper chunk.
This paper may be technical OR non-technical (social science, qualitative, survey-based, etc.)

STRICT RULES:
- DO NOT summarize
- DO NOT infer
- DO NOT speculate
- Extract ONLY what is explicitly stated

Return ONLY valid JSON:
{
  "definitions": [],
  "method_steps": [],
  "results": [],
  "limitations": []
}

For non-technical papers:
- "method_steps" = research design steps (interviews, surveys, sampling, coding themes, etc.)
- "results" = key findings, patterns, themes found
- "limitations" = stated limitations of the study
"""

PAPER_SYNTHESIS_PROMPT = """
You are analyzing a research paper. The paper may be technical OR non-technical
(social science, qualitative, survey-based, humanities, etc.)

The input has two fields:
1. "metadata" — contains title, year, url — COPY THESE EXACTLY into your response
2. "extracted_memory" — facts extracted from the paper

Using extracted_memory, write a thorough explanation covering:
- summary: What is the paper about? What problem does it address?
- methodology: How was the research conducted? (experiments, interviews, surveys, data analysis, etc.)
- key_contributions: What does this paper add that is new or important?
- drawbacks: What are the limitations or weaknesses?

RULES:
- Write in clear prose (not bullet points inside JSON strings)
- Minimum 3-4 sentences per field
- Copy title/year/url from metadata EXACTLY — never leave them blank or as placeholders
- If extracted_memory is sparse, use what IS there and acknowledge gaps honestly
- Do NOT write "Not explicitly stated" — write what you CAN infer from available content

Return ONLY valid JSON (no markdown, no extra text):
{
  "paper_analyses": [
    {
      "title": "<copy metadata.title>",
      "year": "<copy metadata.year>",
      "link": "<copy metadata.url>",
      "summary": "",
      "methodology": "",
      "key_contributions": "",
      "drawbacks": ""
    }
  ]
}
"""

OVERALL_TRENDS_PROMPT = """
Extract overall trends from the analyzed papers.
Consider both technical and non-technical research.

Return ONLY valid JSON:
{
  "themes": [],
  "methods": [],
  "drawbacks": [],
  "evolution": ""
}
"""


# ──────────────────────────────────────────────────────────
# PYDANTIC MODELS
# ──────────────────────────────────────────────────────────

class ChunkExtraction(BaseModel):
    definitions:  List[Dict[str, Any]] = Field(default_factory=list)
    method_steps: List[Dict[str, Any]] = Field(default_factory=list)
    results:      List[Dict[str, Any]] = Field(default_factory=list)
    limitations:  List[Dict[str, Any]] = Field(default_factory=list)


class PaperAnalysis(BaseModel):
    title:             str = ""
    year:              Optional[int | str] = None
    link:              Optional[str] = None
    summary:           Any = ""
    methodology:       Any = ""
    key_contributions: Any = ""
    drawbacks:         Any = ""


class PaperAnalysisResponse(BaseModel):
    paper_analyses: List[PaperAnalysis]


class OverallTrends(BaseModel):
    themes:    List[str] = Field(default_factory=list)
    methods:   List[str] = Field(default_factory=list)
    drawbacks: List[str] = Field(default_factory=list)
    evolution: str = ""


# ──────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────

def clean_llm_json(raw: str) -> str:
    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = re.sub(r"[\x00-\x1F\x7F]", "", raw)
    return raw.strip()


def get_paper_metadata(paper_id: str) -> dict:
    try:
        meta = get_paper_from_index(paper_id)
        if meta and meta.get("title"):
            return {
                "title": meta.get("title", ""),
                "year":  str(meta.get("year", "")),
                "url":   meta.get("url", ""),
            }
    except Exception as e:
        print(f"[Metadata] Chroma lookup failed: {e}")

    try:
        conn = get_connection()
        cur  = conn.cursor()
        cur.execute(
            "SELECT title, published_date, url FROM papers WHERE paper_id = ?",
            (paper_id,)
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "title": row[0] or "",
                "year":  str(row[1] or ""),
                "url":   row[2] or "",
            }
    except Exception as e:
        print(f"[Metadata] SQLite lookup failed: {e}")

    return {"title": "", "year": "", "url": ""}


def _skeleton(metadata: dict, reason: str) -> dict:
    return {
        "title":             metadata.get("title", "Unknown"),
        "year":              metadata.get("year", ""),
        "link":              metadata.get("url", ""),
        "summary":           reason,
        "methodology":       "Not available.",
        "key_contributions": "Not available.",
        "drawbacks":         "Not available.",
    }


# ──────────────────────────────────────────────────────────
# DIRECT SYNTHESIS — used when chunk extraction is sparse
# ──────────────────────────────────────────────────────────

DIRECT_SYNTHESIS_PROMPT = """
You are analyzing a research paper directly from its raw text.
The paper may be technical OR non-technical.

Write a thorough analysis covering:
- summary: What is the paper about?
- methodology: How was the research done?
- key_contributions: What is new or important?
- drawbacks: What are the limitations?

Rules:
- Minimum 3-4 sentences per field
- Copy title/year/url from the metadata provided EXACTLY
- Do NOT write "Not explicitly stated" — derive what you can from the text

Return ONLY valid JSON:
{
  "paper_analyses": [
    {
      "title": "<from metadata>",
      "year": "<from metadata>",
      "link": "<from metadata>",
      "summary": "",
      "methodology": "",
      "key_contributions": "",
      "drawbacks": ""
    }
  ]
}
"""

def synthesise_directly(metadata: dict, raw_text: str) -> PaperAnalysisResponse | None:
    """Fallback: synthesise directly from raw chunk text when extraction is sparse."""
    prompt = json.dumps({
        "metadata":  metadata,
        "raw_text":  raw_text[:4000]
    })
    for strict in [False, True]:
        try:
            system = DIRECT_SYNTHESIS_PROMPT
            if strict:
                system += "\n\nSTRICTLY VALID JSON ONLY. NO MARKDOWN."
            resp = llm_synth.invoke([
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt}
            ])
            return PaperAnalysisResponse.model_validate_json(
                clean_llm_json(resp.content)
            )
        except Exception as e:
            print(f"[DirectSynth] attempt failed: {e}")
    return None


# ──────────────────────────────────────────────────────────
# MAIN AGENT
# ──────────────────────────────────────────────────────────

MIN_CONTENT_WORDS = 50


def analyse(state):
    print("\n--- ANALYSE AGENT ---")

    paper_ids = state.get("active_paper_ids", [])
    if not paper_ids:
        print("[Analysis] No active paper IDs found in state")
        return {"analysis": {"paper_analyses": [], "overall_trends": {}}}

    final_analyses = []

    for paper_id in paper_ids:
        print(f"\n[Analysis] Processing: {paper_id}")

        metadata = get_paper_metadata(paper_id)
        print(f"[Analysis] title='{metadata['title'][:70]}' | year='{metadata['year']}'")

        chunks = get_paper_chunks_by_paper_id(paper_id)

        if not chunks:
            print("[Analysis] No chunks → skeleton")
            final_analyses.append(_skeleton(metadata, "No content available."))
            continue

        total_words = sum(len(c.get("content", "").split()) for c in chunks)
        print(f"[Analysis] Words: {total_words}")

        if total_words < MIN_CONTENT_WORDS:
            print("[Analysis] Too little content → skeleton")
            final_analyses.append(_skeleton(
                metadata,
                "Insufficient full-text content — only abstract/snippet was available."
            ))
            continue

        # ── Chunk extraction ──────────────────────────
        paper_memory = ChunkExtraction()

        def extract_chunk(chunk):
            resp = llm_extract.invoke([
                {"role": "system", "content": CHUNK_EXTRACT_PROMPT},
                {"role": "user",   "content": chunk["content"][:1200]}
            ])
            try:
                return ChunkExtraction.model_validate_json(clean_llm_json(resp.content))
            except Exception:
                return ChunkExtraction()

        with ThreadPoolExecutor(max_workers=1) as executor:
            futures = {executor.submit(extract_chunk, c): c for c in chunks}
            for future in as_completed(futures):
                try:
                    ex = future.result()
                    paper_memory.definitions.extend(ex.definitions)
                    paper_memory.method_steps.extend(ex.method_steps)
                    paper_memory.results.extend(ex.results)
                    paper_memory.limitations.extend(ex.limitations)
                except Exception as e:
                    print(f"[Chunk ERROR] {e}")

        # ── Check if extraction produced useful content ──
        total_extracted = (
            len(paper_memory.definitions) +
            len(paper_memory.method_steps) +
            len(paper_memory.results) +
            len(paper_memory.limitations)
        )
        print(f"[Analysis] Extracted items: {total_extracted}")

        # ── Synthesis ─────────────────────────────────
        parsed = None

        if total_extracted > 0:
            # Normal path: synthesise from extracted memory
            synthesis_input = json.dumps({
                "metadata":         metadata,
                "extracted_memory": paper_memory.model_dump()
            })
            for attempt, strict in enumerate([False, True]):
                try:
                    system = PAPER_SYNTHESIS_PROMPT
                    if strict:
                        system += "\n\nSTRICTLY VALID JSON ONLY. NO MARKDOWN."
                    resp = llm_synth.invoke([
                        {"role": "system", "content": system},
                        {"role": "user",   "content": synthesis_input}
                    ])
                    parsed = PaperAnalysisResponse.model_validate_json(
                        clean_llm_json(resp.content)
                    )
                    break
                except Exception as e:
                    print(f"[Synthesis] Attempt {attempt + 1} failed: {e}")

        if parsed is None:
            # Fallback: synthesise directly from raw text
            print("[Analysis] Sparse extraction → direct synthesis from raw text")
            raw_text = " ".join(c.get("content", "") for c in chunks)
            parsed = synthesise_directly(metadata, raw_text)

        if parsed is None:
            print("[Synthesis] All attempts failed → skeleton")
            final_analyses.append(_skeleton(metadata, "Analysis parsing failed."))
            continue

        # ── Force metadata fields ──────────────────────
        for pa in parsed.paper_analyses:
            if not pa.title: pa.title = metadata["title"]
            if not pa.year:  pa.year  = metadata["year"]
            if not pa.link:  pa.link  = metadata["url"]

        final_analyses.extend([p.dict() for p in parsed.paper_analyses])
        print(f"[Analysis] ✅ {metadata['title'][:60]}")

    # ── Overall trends ────────────────────────────────
    overall_trends = {}
    if final_analyses:
        try:
            resp = llm_trends.invoke([
                {"role": "system", "content": OVERALL_TRENDS_PROMPT},
                {"role": "user",   "content": json.dumps(final_analyses)}
            ])
            overall_trends = OverallTrends.parse_raw(
                clean_llm_json(resp.content)
            ).dict()
        except Exception as e:
            print("[Trends ERROR]", e)

    return {
        "analysis": {
            "paper_analyses": final_analyses,
            "overall_trends": overall_trends
        },
        "analysis_done":     True,
        "has_active_papers": True
    }