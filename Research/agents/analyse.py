import json
import re
import time as _time
from typing import Dict, Any, Optional, List

from pydantic import BaseModel, Field

from config import llm, llm_extract, llm_synth, llm_trends
from tools.tools import get_paper_chunks_by_paper_id, get_connection
from vectore_store.paper_index_store import get_paper_from_index
from db.schema import get_paper_tables
from services.task_manager import add_task_log


# ══════════════════════════════════════════════════════════
# STRICT PYDANTIC MODELS — prevents validation errors
# ══════════════════════════════════════════════════════════

# ── Stage 1: Atomic Evidence Extraction ───────────────────

class EvidenceItem(BaseModel):
    claim: str
    evidence: str
    type: str = "other"          # method | result | comparison | limitation | assumption | design_choice
    section_hint: str = "other"  # introduction | methodology | results | discussion | conclusion | other

class Definition(BaseModel):
    term: str
    definition: str

class EvidenceExtraction(BaseModel):
    paper_type: str = "unclear"
    evidence_items: List[EvidenceItem] = Field(default_factory=list)
    definitions: List[Definition] = Field(default_factory=list)


# ── Stage 2: Global Paper Understanding ───────────────────

class KeyResult(BaseModel):
    metric: str
    value: str
    baseline_comparison: str = ""

class CritiqueScore(BaseModel):
    score: int = 3
    assessment: str = ""

class GlobalUnderstanding(BaseModel):
    core_research_question: str = ""
    novelty: str = ""
    method_summary: str = ""
    experimental_strength: str = ""
    weaknesses: List[str] = Field(default_factory=list)
    missing_baselines: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    scalability: str = ""
    reproducibility: str = ""
    key_results: List[KeyResult] = Field(default_factory=list)
    future_improvements: List[str] = Field(default_factory=list)
    research_impact: str = ""
    
    # Merged Critique Fields
    novelty_score: CritiqueScore = Field(default_factory=CritiqueScore)
    technical_correctness_score: CritiqueScore = Field(default_factory=CritiqueScore)
    experimental_quality_score: CritiqueScore = Field(default_factory=CritiqueScore)
    scalability_score: CritiqueScore = Field(default_factory=CritiqueScore)
    real_world_usability_score: CritiqueScore = Field(default_factory=CritiqueScore)
    reproducibility_score: CritiqueScore = Field(default_factory=CritiqueScore)
    overall_recommendation: str = "borderline"
    key_strengths: List[str] = Field(default_factory=list)
    key_weaknesses: List[str] = Field(default_factory=list)

# ── Stage 4: Cross-Paper Comparison ───────────────────────

class PaperComparison(BaseModel):
    paper: str
    approach: str
    dataset: str = ""
    key_metric: str = ""
    scalability: str = ""

class NoveltyRank(BaseModel):
    paper: str
    rank: int
    reason: str

class ComparativeAnalysis(BaseModel):
    methodology_comparison: List[PaperComparison] = Field(default_factory=list)
    novelty_ranking: List[NoveltyRank] = Field(default_factory=list)
    strongest_experiments: Dict[str, str] = Field(default_factory=dict)
    research_gaps: List[str] = Field(default_factory=list)
    practical_recommendation: Dict[str, str] = Field(default_factory=dict)
    field_evolution: str = ""


# ── Legacy output model (kept for explain agent compatibility) ──

class PaperAnalysis(BaseModel):
    title:             str = ""
    year:              Optional[int | str] = None
    link:              Optional[str] = None
    paper_type:        str = "original_research"
    summary:           Any = ""
    methodology:       Any = ""
    key_contributions: Any = ""
    drawbacks:         Any = ""
    # NEW research-grade fields
    core_research_question: str = ""
    novelty:           str = ""
    experimental_strength: str = ""
    weaknesses:        List[str] = Field(default_factory=list)
    missing_baselines: List[str] = Field(default_factory=list)
    assumptions:       List[str] = Field(default_factory=list)
    scalability:       str = ""
    reproducibility:   str = ""
    key_results:       List[Dict[str, str]] = Field(default_factory=list)
    tables:            List[str] = Field(default_factory=list)  # markdown tables
    critique:          Optional[Dict[str, Any]] = None


# ══════════════════════════════════════════════════════════
# PROMPTS — Multi-Stage Research Reasoning Pipeline
# ══════════════════════════════════════════════════════════

# ── Stage 1: Atomic Evidence Extraction ───────────────────

EVIDENCE_EXTRACT_PROMPT = """
You are extracting ATOMIC EVIDENCE from a research paper chunk.
Each evidence item must be a specific, verifiable claim paired with its supporting data.

For each piece of evidence, capture:
- claim: What is being stated or claimed (be specific, not generic)
- evidence: The specific data, number, metric, or observation supporting it
- type: one of [method, result, comparison, limitation, assumption, design_choice]
- section_hint: your best guess of the paper section [introduction, methodology, results, discussion, conclusion, other]

Also extract key term definitions if present.

RULES:
- Extract ONLY what is explicitly stated in the text
- Be SPECIFIC: "accuracy of 94.3% on CIFAR-10" NOT "good accuracy"
- Capture exact names, numbers, architectures, datasets
- Each evidence item should be ATOMIC — one claim, one piece of evidence
- Ground every extraction in the actual text

Return ONLY valid JSON:
{
  "paper_type": "original_research | review | survey | book_chapter | editorial | unclear",
  "evidence_items": [
    {
      "claim": "...",
      "evidence": "...",
      "type": "method | result | comparison | limitation | assumption | design_choice",
      "section_hint": "introduction | methodology | results | discussion | conclusion | other"
    }
  ],
  "definitions": [
    {"term": "...", "definition": "..."}
  ]
}
"""


# ── Stage 2: Global Paper Understanding ───────────────────

GLOBAL_UNDERSTANDING_PROMPT = """
You are a senior researcher performing a holistic analysis of a research paper.

You are given:
1. "metadata" — title, year, url
2. "evidence" — atomic evidence items extracted from all sections of the paper
3. "tables" — structured tables extracted from the paper (if any)

Analyze the FULL paper coherently. Ground every inference in the provided evidence.
Think like a researcher: WHY does this work matter? WHAT is novel? HOW convincing are the results?

Also act as a NeurIPS reviewer and provide a rigorous critique.
Rate dimensions 1-5 (1=Very Poor, 5=Excellent).

Return ONLY valid JSON:
{
  "core_research_question": "...",
  "novelty": "...",
  "method_summary": "...",
  "experimental_strength": "...",
  "weaknesses": ["..."],
  "missing_baselines": ["..."],
  "assumptions": ["..."],
  "scalability": "...",
  "reproducibility": "...",
  "key_results": [
    {"metric": "...", "value": "...", "baseline_comparison": "..."}
  ],
  "future_improvements": ["..."],
  "research_impact": "...",
  "novelty_score": {"score": 3, "assessment": "..."},
  "technical_correctness_score": {"score": 3, "assessment": "..."},
  "experimental_quality_score": {"score": 3, "assessment": "..."},
  "scalability_score": {"score": 3, "assessment": "..."},
  "real_world_usability_score": {"score": 3, "assessment": "..."},
  "reproducibility_score": {"score": 3, "assessment": "..."},
  "overall_recommendation": "strong_accept | accept | weak_accept | borderline | weak_reject | reject",
  "key_strengths": ["..."],
  "key_weaknesses": ["..."]
}
"""

# ── Stage 4: Cross-Paper Comparative Analysis ─────────────

COMPARATIVE_ANALYSIS_PROMPT = """
You are a research analyst comparing multiple papers on the same topic.

Given analyses of papers below, provide a comparative analysis.
Ground every comparison in specific evidence from the papers.

Return ONLY valid JSON:
{
  "methodology_comparison": [
    {"paper": "title", "approach": "technique used", "dataset": "data used", "key_metric": "best result", "scalability": "assessment"}
  ],
  "novelty_ranking": [{"paper": "title", "rank": 1, "reason": "why most/least novel"}],
  "strongest_experiments": {"paper": "title", "reason": "why strongest"},
  "research_gaps": ["Gap not addressed by any paper"],
  "practical_recommendation": {"paper": "title", "reason": "why most practical"},
  "field_evolution": "How these papers show the field evolving"
}
"""


# ── Direct synthesis fallback ─────────────────────────────

DIRECT_SYNTHESIS_PROMPT = """
You are a senior research scientist analyzing a research paper directly from its raw text.

FIRST: Determine the paper type:
- If this is a BOOK CHAPTER, REVIEW PAPER, SURVEY, or EDITORIAL with no original experiments:
  Set paper_type accordingly and keep analysis brief.
- If this is ORIGINAL RESEARCH: provide a thorough, technically specific analysis.

Think like a researcher: WHY does this work matter? WHAT is novel? HOW convincing are results?
Ground every inference in evidence from the text.

Return ONLY valid JSON:
{
  "core_research_question": "...",
  "novelty": "...",
  "method_summary": "...",
  "experimental_strength": "...",
  "weaknesses": ["..."],
  "missing_baselines": ["..."],
  "assumptions": ["..."],
  "scalability": "...",
  "reproducibility": "...",
  "key_results": [{"metric": "...", "value": "...", "baseline_comparison": "..."}],
  "future_improvements": ["..."],
  "research_impact": "...",
  "paper_type": "original_research | review | survey | book_chapter | editorial"
}
"""


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

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


# ── Rate-limit-aware LLM call ─────────────────────────────

def _invoke_with_retry(llm_instance, messages, max_retries=2, base_wait=15):
    """Invoke LLM with automatic retry on 429 rate limit errors."""
    for attempt in range(max_retries + 1):
        try:
            return llm_instance.invoke(messages)
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "rate_limit" in error_str.lower():
                if attempt < max_retries:
                    wait = base_wait * (attempt + 1)
                    print(f"[Rate Limit] Waiting {wait}s before retry {attempt + 2}/{max_retries + 1}...")
                    _time.sleep(wait)
                else:
                    print(f"[Rate Limit] All {max_retries + 1} attempts exhausted.")
                    raise
            else:
                raise


def _batch_chunks(chunks: list, batch_size: int) -> list:
    """Group chunks into batches for efficient LLM calls."""
    batches = []
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        combined_text = "\n\n---\n\n".join(c.get("content", "") for c in batch)
        batches.append(combined_text)
    return batches


# ══════════════════════════════════════════════════════════
# STAGE FUNCTIONS
# ══════════════════════════════════════════════════════════

MIN_CONTENT_WORDS = 50
CHUNKS_PER_BATCH  = 4  # Group 4 chunks per LLM call


def _run_evidence_extraction(chunks: list) -> tuple[EvidenceExtraction, list[str]]:
    """
    Stage 1: Extract atomic evidence from paper chunks in batches.
    Returns (merged evidence, list of paper_type votes).
    """
    merged = EvidenceExtraction()
    type_votes = []
    batches = _batch_chunks(chunks, CHUNKS_PER_BATCH)
    print(f"[Stage 1] Batched {len(chunks)} chunks into {len(batches)} calls")

    for batch_idx, batch_text in enumerate(batches):
        try:
            resp = _invoke_with_retry(llm_extract, [
                {"role": "system", "content": EVIDENCE_EXTRACT_PROMPT},
                {"role": "user",   "content": batch_text}
            ])
            ex = EvidenceExtraction.model_validate_json(clean_llm_json(resp.content))
            merged.evidence_items.extend(ex.evidence_items)
            merged.definitions.extend(ex.definitions)
            if ex.paper_type and ex.paper_type != "unclear":
                type_votes.append(ex.paper_type)
            print(f"[Stage 1] Batch {batch_idx + 1}/{len(batches)} ({len(ex.evidence_items)} items)")
            if batch_idx < len(batches) - 1:
                _time.sleep(2)  # Proactive throttling
        except Exception as e:
            print(f"[Stage 1 ERROR] Batch {batch_idx + 1}: {e}")

    return merged, type_votes


def _run_global_understanding(metadata: dict, evidence: EvidenceExtraction, tables: list) -> GlobalUnderstanding | None:
    """
    Stage 2: Generate holistic paper understanding from all evidence + tables.
    """
    tables_text = ""
    if tables:
        tables_text = "\n\n".join(
            f"### Table (Page {t.get('page', '?')}):\n{t['markdown']}"
            for t in tables[:5]  # limit to 5 tables to stay within token budget
        )

    # Compress payload to save tokens
    compressed_evidence = "\n".join(
        f"- [{item.type.upper()}] {item.claim}: {item.evidence} (Section: {item.section_hint})"
        for item in evidence.evidence_items[:30]
    )
    compressed_defs = "\n".join(
        f"- {d.term}: {d.definition}" for d in evidence.definitions[:5]
    )
    
    input_data = json.dumps({
        "metadata": metadata,
        "evidence_text": compressed_evidence,
        "definitions_text": compressed_defs,
        "tables": tables_text
    })

    for attempt in range(2):
        try:
            system = GLOBAL_UNDERSTANDING_PROMPT
            if attempt == 1:
                system += "\n\nSTRICTLY VALID JSON ONLY. NO MARKDOWN."
            resp = _invoke_with_retry(llm_synth, [
                {"role": "system", "content": system},
                {"role": "user",   "content": input_data}
            ])
            return GlobalUnderstanding.model_validate_json(clean_llm_json(resp.content))
        except Exception as e:
            print(f"[Stage 2] Attempt {attempt + 1} failed: {e}")

    return None





def _run_comparative_analysis(all_analyses: list[dict]) -> ComparativeAnalysis | None:
    """
    Stage 4: Cross-paper comparative intelligence.
    """
    if len(all_analyses) < 2:
        return None

    input_data = json.dumps(all_analyses)

    for attempt in range(2):
        try:
            system = COMPARATIVE_ANALYSIS_PROMPT
            if attempt == 1:
                system += "\n\nSTRICTLY VALID JSON ONLY. NO MARKDOWN."
            resp = _invoke_with_retry(llm_trends, [
                {"role": "system", "content": system},
                {"role": "user",   "content": input_data}
            ])
            return ComparativeAnalysis.model_validate_json(clean_llm_json(resp.content))
        except Exception as e:
            print(f"[Stage 4] Attempt {attempt + 1} failed: {e}")

    return None


def _run_direct_synthesis(metadata: dict, raw_text: str, tables: list) -> dict | None:
    """Fallback: synthesise directly from raw text when evidence extraction is sparse."""
    tables_text = ""
    if tables:
        tables_text = "\n\n".join(
            f"### Table (Page {t.get('page', '?')}):\n{t['markdown']}"
            for t in tables[:3]
        )

    prompt = json.dumps({
        "metadata": metadata,
        "raw_text": raw_text[:4000],
        "tables": tables_text
    })

    for attempt in range(2):
        try:
            system = DIRECT_SYNTHESIS_PROMPT
            if attempt == 1:
                system += "\n\nSTRICTLY VALID JSON ONLY. NO MARKDOWN."
            resp = _invoke_with_retry(llm_synth, [
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt}
            ])
            return json.loads(clean_llm_json(resp.content))
        except Exception as e:
            print(f"[DirectSynth] Attempt {attempt + 1} failed: {e}")

    return None


# ══════════════════════════════════════════════════════════
# MAIN ANALYSE AGENT
# ══════════════════════════════════════════════════════════

def analyse(state):
    print("\n" + "="*70, flush=True)
    print("ANALYSE AGENT (RESEARCH INTELLIGENCE) RUNNING", flush=True)
    print("="*70, flush=True)

    paper_ids = state.get("active_paper_ids", [])
    if not paper_ids:
        print("[Analysis] No active paper IDs found in state", flush=True)
        print("="*70 + "\n", flush=True)
        return {"analysis": {"paper_analyses": [], "overall_trends": {}}}

    final_analyses = []

    for paper_id in paper_ids:
        print(f"\n{'='*60}", flush=True)
        print(f"[Analysis] Processing: {paper_id}", flush=True)

        metadata = get_paper_metadata(paper_id)
        print(f"[Analysis] title='{metadata['title'][:70]}' | year='{metadata['year']}'", flush=True)
        add_task_log(state.get("task_id"), f"[Analyse] Processing paper: {metadata['title'][:70]}")

        # ── Fetch chunks ──
        chunks = get_paper_chunks_by_paper_id(paper_id)

        if not chunks:
            print("[Analysis] No chunks → skeleton", flush=True)
            final_analyses.append(_skeleton(metadata, "No content available."))
            continue

        total_words = sum(len(c.get("content", "").split()) for c in chunks)
        print(f"[Analysis] Words: {total_words} | Chunks: {len(chunks)}", flush=True)

        if total_words < MIN_CONTENT_WORDS:
            print("[Analysis] Too little content → skeleton", flush=True)
            final_analyses.append(_skeleton(
                metadata,
                "Insufficient full-text content — only abstract/snippet was available."
            ))
            continue

        # ── Fetch tables (Table RAG) ──
        tables = get_paper_tables(paper_id)
        if tables:
            print(f"[Analysis] Found {len(tables)} table(s) for this paper", flush=True)

        # ══════════════════════════════════════════════════
        # STAGE 1 — Atomic Evidence Extraction
        # ══════════════════════════════════════════════════
        print(f"\n[Stage 1] Evidence Extraction...", flush=True)
        evidence, type_votes = _run_evidence_extraction(chunks)

        # ── Paper type filter (safety net) ────────────
        NON_RESEARCH_TYPES = {"review", "survey", "book_chapter", "editorial"}
        if type_votes:
            from collections import Counter
            vote_counts = Counter(type_votes)
            dominant_type = vote_counts.most_common(1)[0][0]
            print(f"[Analysis] Paper type votes: {dict(vote_counts)} → dominant: {dominant_type}", flush=True)
            if dominant_type in NON_RESEARCH_TYPES:
                print(f"\n REJECTED: '{metadata['title'][:60]}' (Type: {dominant_type})", flush=True)
                print("="*70, flush=True)
                continue

        total_evidence = len(evidence.evidence_items)
        print(f"[Analysis] Total evidence items: {total_evidence} | Definitions: {len(evidence.definitions)}", flush=True)

        # ══════════════════════════════════════════════════
        # STAGE 2 — Global Paper Understanding
        # ══════════════════════════════════════════════════
        understanding = None

        if total_evidence > 0:
            print(f"\n[Stage 2] Global Paper Understanding...", flush=True)
            understanding = _run_global_understanding(metadata, evidence, tables)
            if understanding:
                print(f"[Stage 2] Understanding complete", flush=True)
            else:
                print(f"[Stage 2]  Failed")

        # Fallback to direct synthesis if evidence or understanding failed
        if understanding is None:
            print("[Analysis] Sparse evidence → direct synthesis from raw text")
            raw_text = " ".join(c.get("content", "") for c in chunks)
            direct_result = _run_direct_synthesis(metadata, raw_text, tables)

            if direct_result:
                # Build analysis from direct synthesis
                analysis_entry = {
                    "title":               metadata.get("title", "Unknown"),
                    "year":                metadata.get("year", ""),
                    "link":                metadata.get("url", ""),
                    "paper_type":          direct_result.get("paper_type", "original_research"),
                    "summary":             direct_result.get("method_summary", ""),
                    "methodology":         direct_result.get("method_summary", ""),
                    "key_contributions":   direct_result.get("novelty", ""),
                    "drawbacks":           ", ".join(direct_result.get("weaknesses", [])),
                    "core_research_question": direct_result.get("core_research_question", ""),
                    "novelty":             direct_result.get("novelty", ""),
                    "experimental_strength": direct_result.get("experimental_strength", ""),
                    "weaknesses":          direct_result.get("weaknesses", []),
                    "missing_baselines":   direct_result.get("missing_baselines", []),
                    "assumptions":         direct_result.get("assumptions", []),
                    "scalability":         direct_result.get("scalability", ""),
                    "reproducibility":     direct_result.get("reproducibility", ""),
                    "key_results":         direct_result.get("key_results", []),
                    "tables":              [t["markdown"] for t in tables] if tables else [],
                    "future_improvements": direct_result.get("future_improvements", []),
                    "research_impact":     direct_result.get("research_impact", ""),
                    "critique":            None,
                }
                final_analyses.append(analysis_entry)
                print(f"[Analysis] (direct synthesis) {metadata['title'][:60]}")
                continue
            else:
                print("[Analysis] All synthesis failed → skeleton")
                final_analyses.append(_skeleton(metadata, "Analysis parsing failed."))
                continue

        

        # ══════════════════════════════════════════════════
        # Build final analysis for this paper
        # ══════════════════════════════════════════════════
        analysis_entry = {
            "title":               metadata.get("title", "Unknown"),
            "year":                metadata.get("year", ""),
            "link":                metadata.get("url", ""),
            "paper_type":          "original_research",
            # Legacy fields (for backward compat with explain agent)
            "summary":             understanding.method_summary,
            "methodology":         understanding.method_summary,
            "key_contributions":   understanding.novelty,
            "drawbacks":           ", ".join(understanding.weaknesses),
            # NEW research-grade fields
            "core_research_question": understanding.core_research_question,
            "novelty":             understanding.novelty,
            "experimental_strength": understanding.experimental_strength,
            "weaknesses":          understanding.weaknesses,
            "missing_baselines":   understanding.missing_baselines,
            "assumptions":         understanding.assumptions,
            "scalability":         understanding.scalability,
            "reproducibility":     understanding.reproducibility,
            "key_results":         [r.model_dump() for r in understanding.key_results],
            "tables":              [t["markdown"] for t in tables] if tables else [],
            "future_improvements": understanding.future_improvements,
            "research_impact":     understanding.research_impact,
            "critique": {
                "novelty": understanding.novelty_score.model_dump(),
                "technical_correctness": understanding.technical_correctness_score.model_dump(),
                "experimental_quality": understanding.experimental_quality_score.model_dump(),
                "scalability": understanding.scalability_score.model_dump(),
                "real_world_usability": understanding.real_world_usability_score.model_dump(),
                "reproducibility": understanding.reproducibility_score.model_dump(),
                "overall_recommendation": understanding.overall_recommendation,
                "key_strengths": understanding.key_strengths,
                "key_weaknesses": understanding.key_weaknesses,
            } if understanding else None,
        }

        final_analyses.append(analysis_entry)
        print(f"\nACCEPTED: '{metadata['title'][:60]}'", flush=True)
        if analysis_entry.get("critique"):
            scores = analysis_entry["critique"]
            print(f"   📊 SCORES:", flush=True)
            print(f"      • Novelty: {scores['novelty']['score']}/10", flush=True)
            print(f"      • Technical Correctness: {scores['technical_correctness']['score']}/10", flush=True)
            print(f"      • Experimental Quality: {scores['experimental_quality']['score']}/10", flush=True)
            print(f"      • Scalability: {scores['scalability']['score']}/10", flush=True)
            print(f"      • Real-world Usability: {scores['real_world_usability']['score']}/10", flush=True)
            print(f"      • Reproducibility: {scores['reproducibility']['score']}/10", flush=True)
            print(f"      • Recommendation: {scores['overall_recommendation']}", flush=True)
        print("="*70, flush=True)

    # ══════════════════════════════════════════════════════
    # STAGE 4 — Cross-Paper Comparative Analysis
    # ══════════════════════════════════════════════════════
    comparative = {}
    if len(final_analyses) >= 2:
        print(f"\n[Stage 4] Cross-Paper Comparative Analysis ({len(final_analyses)} papers)...")
        comp = _run_comparative_analysis(final_analyses)
        if comp:
            comparative = comp.model_dump()
            print(f"[Stage 4] Comparison complete")
        else:
            print(f"[Stage 4]  Comparison failed (non-fatal)")

    print(f"\n{'='*70}")
    print(f" ANALYSIS COMPLETE: {len(final_analyses)} PAPERS ANALYZED")
    print(f"{'='*70}")
    for i, analysis in enumerate(final_analyses, 1):
        print(f"   [{i}] {analysis['title'][:65]}")
    print(f"{'='*70 + chr(10)}")

    return {
        "analysis": {
            "paper_analyses": final_analyses,
            "overall_trends": comparative,  # now contains richer comparative analysis
        },
        "analysis_done":     True,
        "has_active_papers": True
    }