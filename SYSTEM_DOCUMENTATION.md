# Research Paper Analysis System - Complete Documentation

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Diagram](#architecture-diagram)
3. [Workflow Steps](#workflow-steps)
4. [Crucial Components & How They Work](#crucial-components--how-they-work)
5. [Important Implementation Details](#important-implementation-details)
6. [Edge Cases & Handling](#edge-cases--handling)
7. [Key Decision Points](#key-decision-points)

---

## System Overview

This is a **Multi-Agent Research Paper Analysis System** that:

- Takes user queries about research topics
- Decides whether to retrieve from database or fetch from web
- Fetches and scores research papers (filtering out non-research content)
- Analyzes papers using a 4-stage pipeline with LLM calls
- Generates researcher-grade reviews with scoring
- Supports follow-up questions on analyzed papers

**Tech Stack:**

- Backend: Python + Flask
- LLM: Claude (multiple models for different tasks)
- Vector DB: Chroma (in-memory)
- SQL DB: SQLite
- Frontend: React + Vite
- Search: Semantic Scholar API + Tavily

---

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           FLASK BACKEND (main.py)                        │
│                         HTTP REST API Server                             │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                │                             │
    ┌───────────▼────────────┐    ┌──────────▼──────────┐
    │  POST /api/task        │    │  GET /api/task/{id} │
    │  Create new research   │    │  Check status       │
    └───────────┬────────────┘    └────────────────────┘
                │
                ▼
    ┌───────────────────────────────────────────┐
    │      agent_runner.py: run_task()          │
    │   Orchestrates entire workflow            │
    │   - Session management (in-memory + Redis)│
    │   - State persistence                     │
    │   - Task logging                          │
    └───────┬──────────────────────────────────┘
            │
            ▼
    ┌─────────────────────────────────────────────────┐
    │         build_graph() - LanGraph                │
    │   Builds agent workflow graph                   │
    └──────────┬──────────────────────────────────────┘
               │
    ┌──────────┴─────────────────────────────────────────┐
    │                                                    │
    ▼ (Agent Flow)                                       │
┌─────────────────────────────────────────────────────────────────────┐
│                      DECISION AGENT                              │
│  INPUT: user query + existing papers state                          │
│  DECISION:                                                           │
│    ├─ new_topic → go to RETRIEVE_FROM_DB                           │
│    ├─ continuation → go to CONTINUOUS_EXPLANATION                  │
│    ├─ general_question → go to CONTINUOUS_EXPLANATION              │
│    └─ end → END                                                     │
│  OUTPUT: next_step routing decision                                 │
└─────────────────────────────────────────────────────────────────────┘
    │
    ├────────────────────────────────────────────────────────┐
    │                                                        │
    ▼ (if new_topic & not retrieval_attempted)              ▼ (if continuation/general_question)
┌─────────────────────────────────┐                    ┌──────────────────────────────┐
│    DB RETRIEVAL AGENT         │                    │ 💬 CONTINUOUS EXPLANATION   │
│ ─────────────────────────────   │                    │ ──────────────────────────   │
│ 1. Search Chroma vector DB      │                    │ 1. Get existing paper chunks │
│ 2. Similarity match on abstract │                    │ 2. LLM answer from context   │
│ 3. Confidence filter > 0.75     │                    │ 3. Fallback: Tavily web      │
│ 4. Return top K papers          │                    │    search if insufficient    │
│ OUTPUT: paper list              │                    │ OUTPUT: explanation          │
└────────────────────┬────────────┘                    └──────────────────────────────┘
                     │                                          │
                     ▼                                          ▼
            ┌────────────────────────┐                    END: Return to Frontend
            │ Back to DECISION       │
            │ (next cycle)           │
            └────────────────────────┘
    │
    ├────────────────────────────────────────────────────────────┐
    │                                                            │
    ▼ (if retrieval_attempted & no papers in DB)               │
┌────────────────────────────────────────────────────────────────┐
│             🌐 FETCH AGENT (Web Retrieval)                     │
│ ────────────────────────────────────────────────────           │
│ 1. Query rewrite with LLM                                     │
│ 2. 3 PDF search rounds (expanding query):                     │
│    • Round 1: optimized_query                                 │
│    • Round 2: optimized_query + "open access arxiv"           │
│    • Round 3: optimized_query + "novel method experiment"     │
│ 3. For each paper:                                            │
│    ├─ Score relevance (0-100)                                 │
│    ├─ Filter by paper type (must be original_research)        │
│    ├─ Filter by year range (if specified)                     │
│    ├─ Try to get PDF or fallback to abstract                  │
│    └─ Parse PDF → extract text & tables                       │
│ 4. Store papers in:                                           │
│    ├─ Chroma (vector DB for chunks)                           │
│    ├─ SQLite (metadata)                                       │
│    └─ Index (for quick lookup)                                │
│ 5. Prioritize: PDF papers → Abstract papers                   │
│ OUTPUT: stored_paper_ids list                                 │
└─────────────────────┬──────────────────────────────────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │ Back to DECISION     │
            │ has_active_papers=✓  │
            │ analysis_done=✗      │
            └──────────────────────┘
    │
    ├────────────────────────────────────────────────────────────┐
    │                                                            │
    ▼ (if has_active_papers & not analysis_done)               │
┌────────────────────────────────────────────────────────────────┐
│          🔬 ANALYSE AGENT (Research Intelligence)              │
│ ────────────────────────────────────────────────────           │
│                                                                │
│ FOR EACH PAPER:                                               │
│                                                                │
│ STAGE 1: Atomic Evidence Extraction                           │
│ ├─ Split chunks into batches (4 per batch)                   │
│ ├─ LLM extracts atomic evidence items (EVIDENCE_EXTRACT)     │
│ ├─ Collect: claim, evidence, type, section_hint              │
│ ├─ Paper type voting (most common = dominant)                │
│ └─ If non-research type → REJECT paper                        │
│                                                                │
│ STAGE 2: Global Paper Understanding                           │
│ ├─ Compress evidence & tables into JSON                       │
│ ├─ LLM generates holistic understanding (GLOBAL_UNDERSTAND)  │
│ ├─ Includes:                                                  │
│ │  • Core research question                                   │
│ │  • Novelty assessment                                       │
│ │  • Method summary                                           │
│ │  • 6 critique scores (1-5 scale each):                      │
│ │    - Novelty                                                │
│ │    - Technical Correctness                                  │
│ │    - Experimental Quality                                   │
│ │    - Scalability                                            │
│ │    - Real-world Usability                                   │
│ │    - Reproducibility                                        │
│ │  • Overall recommendation (accept/reject/borderline)        │
│ │  • Key strengths & weaknesses                               │
│ └─ Fallback: Direct synthesis if evidence sparse              │
│                                                                │
│ STAGE 4: Cross-Paper Comparative Analysis (if 2+ papers)     │
│ ├─ LLM compares all papers (COMPARATIVE_ANALYSIS)            │
│ ├─ Outputs:                                                   │
│ │  • Methodology comparison (table format)                    │
│ │  • Novelty ranking                                          │
│ │  • Strongest experiments                                    │
│ │  • Research gaps                                            │
│ │  • Practical recommendations                                │
│ │  • Field evolution narrative                                │
│ └─ Stored in overall_trends                                   │
│                                                                │
│ OUTPUT: analysis dict with:                                   │
│   - paper_analyses: [per-paper analysis objects]              │
│   - overall_trends: cross-paper comparative analysis          │
└─────────────────────┬──────────────────────────────────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │ → EXPLAIN AGENT      │
            └──────────────────────┘
    │
    └────────────────────────────────────────────────────────────┐
                                                                │
    ▼ (Final step)                                             │
┌────────────────────────────────────────────────────────────────┐
│            💬 EXPLANATION AGENT                                 │
│ ───────────────────────────────────────────────────           │
│ 1. Takes analysis + original user query                       │
│ 2. LLM generates researcher-grade review                      │
│ 3. Format: Detailed review for EACH paper with:              │
│    • Title, Year, Link, Paper Type                            │
│    • Core Research Question                                   │
│    • Novelty Assessment                                       │
│    • Methodology Details                                      │
│    • Key Results (with tables embedded)                       │
│    • Experimental Strength                                    │
│    • Weaknesses & Missing Baselines                           │
│    • Assumptions & Scalability                                │
│    • Reproducibility Assessment                               │
│    • Reviewer Verdict (with scores & recommendation)          │
│ 4. Then: Cross-paper analysis (if available)                 │
│ OUTPUT: explanation (markdown text)                           │
└─────────────────────┬──────────────────────────────────────────┘
                      │
                      ▼
            ┌──────────────────────┐
            │ END: Return Results  │
            │ to Frontend via API  │
            └──────────────────────┘
```

---

## Workflow Steps

### Step 1: User Query Submission (Frontend → Backend)

```
POST /api/task
{
  "query": "machine learning transformers",
  "year_from": 2020,
  "year_to": 2025
}
↓
Returns: {
  "task_id": "16f56a53-0b7b-4e84-...",
  "session_id": "new_session_uuid"
}
```

### Step 2: Decision Agent Classifies Intent

**Input:** User query + current state (has analyzed papers? analysis done?)

**Classification Logic:**

```python
if user just provided topic name or "find papers" → "new_topic"
elif user asks about already-analyzed papers → "continuation"
elif user asks concept question (what/how/why) → "general_question"
elif user says thanks/done/bye → "end"
```

**Output:** Routing decision (next agent to run)

### Step 3A: DB Retrieval (If New Topic & DB Has Papers)

1. **Similarity Search:** Query → Chroma embedding → top-K papers
2. **Filtering:** Only papers with confidence > 0.75
3. **Return:** List of paper objects from database

### Step 3B: Web Fetch (If DB Empty or Papers Not Found)

1. **Query Rewrite:** LLM optimizes user query
2. **3-Round Search:**
   - Round 1: Basic query
   - Round 2: Basic query + "open access arxiv preprint"
   - Round 3: Basic query + "novel method experiment results"
3. **Paper Scoring:**
   - LLM scores each paper 0-100
   - Must be "original_research" type (not review/survey/book)
   - Must pass year filter (if specified)
4. **PDF Resolution:**
   - Try multiple sources: pdf_url → arXiv → Semantic Scholar → Unpaywall → MDPI scrape
5. **Storage:**
   - Chroma: Full text chunks (for retrieval)
   - SQLite: Metadata + tables
   - Index: Quick lookup

### Step 4: Analysis (4-Stage Intelligence Pipeline)

#### Stage 1: Atomic Evidence Extraction

- **Batch chunks:** 4 chunks per LLM call
- **Extract:** Claims, evidence, type, section
- **Vote:** Paper type (research/review/survey/etc.)
- **Filter:** Reject non-research papers

#### Stage 2: Global Understanding

- **Synthesize:** All evidence → holistic understanding
- **Generate:** Research question, novelty, methods, results
- **Score:** 6 dimensions (1-5 each)
- **Recommend:** Accept/Borderline/Reject

#### Stage 4: Comparative Analysis (2+ papers)

- **Compare:** Methodologies, novelty ranking
- **Identify:** Research gaps, practical recommendations
- **Narrative:** How field is evolving

### Step 5: Explanation Generation

- **Format:** Researcher-grade review (markdown)
- **Per-paper:** All analysis fields + verdict
- **Cross-paper:** Comparative insights
- **Return:** To frontend as formatted text

### Step 6: Follow-up Questions

User asks about already-analyzed papers:

- **Retrieve:** Chunks from Chroma for those papers
- **LLM:** Answers from context or Tavily fallback
- **Return:** Direct answer

---

## Crucial Components & How They Work

### 1. **Decision Agent (agents/decision.py)**

**What it does:** Routes every user interaction to the right agent

**How it works:**

```python
# Input: user_query + has_active_papers + analysis_done
# LLM classification with detailed prompt

if intent == "end":
    → END
elif intent in ("continuation", "general_question"):
    → CONTINUOUS_EXPLANATION (answer from existing papers)
elif intent == "new_topic":
    if not retrieval_attempted:
        → DB (try database first)
    elif retrieval_attempted and no papers:
        → FETCH (go to web)
    elif has papers and not analyzed:
        → ANALYSE (analyze fetched papers)
```

**Why it matters:** Single point of control for entire workflow

---

### 2. **Fetch Agent (agents/fetch.py) - The Gatekeeper**

**What it does:** Filters out non-research content, ensures quality papers only

**Critical filtering logic:**

```python
# Paper Type Check (HEURISTIC + LLM)
NON_RESEARCH_KEYWORDS = [
    "introduction to", "a survey of", "tutorial",
    "handbook", "textbook", "review of"
]

is_likely_non_research(title, abstract, url):
    if any keyword in title.lower():
        return True  # Fast reject
    if "this book" or "this chapter" in abstract.lower():
        return True  # Fast reject

# LLM SCORING
score_paper(title, abstract, query):
    if is_likely_non_research(): return 0
    if llm_says_non_research(): return 0  # Force zero
    return relevance_score (0-100)

# ACCEPT CRITERIA
✓ paper_type == "original_research"
✓ score >= 54 (threshold)
✓ year in [year_from, year_to]
✓ pdf available OR abstract fallback
```

**Why it matters:**

- Prevents analysis of non-research content (wasted LLM calls)
- Enforces quality threshold
- Scores papers relevantly to user query

---

### 3. **Analyse Agent (agents/analyse.py) - The Intelligence Engine**

**What it does:** Multi-stage LLM analysis of papers

**Stage 1: Evidence Extraction**

```
Each chunk batched (4 chunks per call)
↓
LLM extracts atomic facts:
  - claim: "The model achieved 94.3% accuracy"
  - evidence: "On CIFAR-10 test set"
  - type: "result"
  - section: "results"
↓
Collect paper type votes
↓
If dominant type = "review" → REJECT entire paper
```

**Stage 2: Global Understanding**

```
ALL evidence items + tables
↓
LLM generates:
  - novelty (what's new vs prior work)
  - method_summary (exact techniques used)
  - experimental_strength (how well tested)
  - 6 critique scores (NeurIPS reviewer style)
  - overall_recommendation (accept/reject/borderline)
↓
Output: GlobalUnderstanding object
```

**Stage 4: Comparative Analysis**

```
All paper analyses
↓
LLM compares:
  - methodology_comparison (which approach best)
  - novelty_ranking (most to least novel)
  - research_gaps (what nobody addresses)
  - practical_recommendation (which to implement)
↓
Output: ComparativeAnalysis object
```

**Why it matters:**

- Multi-LLM approach: different models for different tasks (extract, synthesize, trend)
- Token optimization: batching, compression, limiting to top tables
- Scoring enables filtering in frontend
- Fallback to direct synthesis if evidence sparse

---

### 4. **Progress Hook (services/progress_hook.py) - Status Tracking**

**What it does:** Marks each agent as "running" → "done"

**Why it matters:**

- Frontend polls task status every 2 seconds
- Shows user which agent is working
- Logs all steps for debugging
- Prevents UI from appearing stuck

---

### 5. **Session Management (services/agent_runner.py)**

**How it works:**

```
1. NEW SESSION:
   ├─ In-memory store (fast, guaranteed sync)
   ├─ Redis backup (for multi-instance scaling)
   └─ Chroma reset (fresh vector DB)

2. EXISTING SESSION:
   ├─ Load state from in-memory
   ├─ Keep existing papers
   ├─ Continue analysis or ask new question
   └─ Preserve task logs

3. STATE PERSISTENCE:
   └─ State saved after EVERY agent completes
```

**Why it matters:**

- Users can ask follow-up questions without re-fetching
- Handles server restarts (Redis backup)
- Chroma in-memory = ultra-fast chunking

---

## Important Implementation Details

### 1. **Flush=True on All Print Statements**

```python
print("Message", flush=True)  # Immediately visible in Flask
```

**Why:** Flask buffers output by default. Without flush=True, prints appear only when process exits.

### 2. **Rate Limit Handling**

```python
def _invoke_with_retry(llm_instance, messages, max_retries=2, base_wait=15):
    for attempt in range(max_retries + 1):
        try:
            return llm_instance.invoke(messages)
        except RateLimitError:
            wait = base_wait * (attempt + 1)  # 15s, 30s, 45s
            sleep(wait)
            retry...
```

**Why:** Claude hits rate limits on heavy analysis. Exponential backoff prevents cascade failures.

### 3. **Token Optimization (Analyse Agent)**

```python
# Compress evidence (limit to 30 items)
compressed_evidence = "\n".join(items[:30])

# Limit tables (top 5 per paper)
tables_subset = tables[:5]

# Send as JSON (not raw text)
input_data = json.dumps({
    "metadata": {...},
    "evidence": compressed_evidence,
    "tables": tables_subset
})
```

**Why:** LLM calls are expensive. Trimming non-critical info saves tokens & cost.

### 4. **Paper Type Voting (Safety Net)**

```python
# Evidence extraction returns paper_type for EACH batch
type_votes = [vote1, vote2, vote3, ...]
dominant_type = Counter(type_votes).most_common(1)

if dominant_type in NON_RESEARCH_TYPES:
    print(f"REJECTED: Non-research paper ({dominant_type})")
    continue  # Skip to next paper
```

**Why:** Catches edge cases where LLM misclassifies (e.g., textbook chapter as research).

### 5. **Chroma Vector DB (In-Memory)**

```python
# All papers stored in single in-memory Chroma collection
add_paper_chunks(paper_id, full_text):
    # Chunks text + creates embeddings
    # Stored with paper_id for later retrieval

# For follow-up questions:
get_chunks_for_papers(paper_ids, user_query):
    # Retrieves TOP chunks matching question
    # Passed to LLM for context-aware answering
```

**Why:** Fast similarity search without database round-trip.

### 6. **PDF Parsing & Table Extraction**

```python
parsed = parse_paper(pdf_path):
    returns {
        "full_text": str,
        "tables": [
            {
                "page": 3,
                "markdown": "| Col1 | Col2 |\n|------|------|"
            }
        ]
    }
```

**Why:** Tables are structured data. Embedding them separately improves analysis accuracy.

---

## Edge Cases & Handling

### Edge Case 1: User Provides Topic Name Without "Find Papers"

```
User: "LSTM"
Decision Agent thinks: "What is LSTM?" → "general_question"
FIX: Prompt explicitly says: "topic name alone = new_topic intent"
```

### Edge Case 2: Paper Title Looks Like Research But Is Review

```
Title: "A Comprehensive Survey on Transformers"
Heuristic: "survey" keyword → fast reject ✓
LLM Scorer: Still marks type="survey" → score forced to 0 ✓
Analysis: Evidence extraction votes "survey" → paper rejected ✓
Outcome: Triple filtered, never analyzed
```

### Edge Case 3: PDF Downloaded But Parsing Fails

```
parse_paper(pdf) → returns None or empty text
Analysis detects: total_words < MIN_CONTENT_WORDS (50)
Fallback: Uses abstract instead (already stored)
Outcome: Analysis completes with reduced depth
```

### Edge Case 4: Year Filter Excludes All Papers

```
year_from=2024, year_to=2024
Fetch searches for 2 rounds → all papers outside range → rejected
remaining = target - len(pdf_papers) > 0
Abstract fallback: Tries to fill slots with abstracts
If STILL empty → task completes with "0 papers found"
```

### Edge Case 5: LLM Returns Malformed JSON

```
_run_evidence_extraction():
    try:
        EvidenceExtraction.model_validate_json(response)
    except:
        print(f"[Stage 1 ERROR] Batch {idx}: {e}")
        Continue to next batch (partial evidence acceptable)

_run_global_understanding():
    For attempt in range(2):
        try:
            return GlobalUnderstanding.model_validate_json(...)
        except Exception:
            if attempt == 1: system += "\n\nSTRICTLY VALID JSON ONLY"
            retry with stricter prompt
    If both fail: Fallback to _run_direct_synthesis()
```

### Edge Case 6: Session Expires (30 minutes no activity)

```
SESSION_TTL = 1800  # 30 seconds

load_state(session_id):
    1. Check in-memory store (fastest)
    2. Check Redis (backup)
    3. If both empty → Create new session

Result: User loses context but can still search
```

### Edge Case 7: Chroma Collection Empty (No Papers Indexed)

```
get_chunks_for_papers(paper_ids, query):
    if col is None or col.count() == 0:
        print("[Continuation] Chroma collection is empty")
        return []

Continuous Explanation falls back to Tavily web search
```

### Edge Case 8: User Asks Question About Non-Existent Papers

```
User: "What about the third paper?"
State.active_paper_ids = [paper1, paper2]  # Only 2 papers
Continuous Explanation: Gets 0 chunks for non-existent paper
Falls back to web search
Result: Generic web answer rather than paper-specific
```

---

## Key Decision Points

### Decision Point 1: DB vs Web Fetch

```python
if not retrieval_attempted:
    → Try DB first (FASTER, cached)
elif retrieval_attempted and not has_active_papers:
    → Go to WEB (DB was empty, expand search)
```

**Rationale:** Local DB is faster. Only hit web API if needed.

### Decision Point 2: Accept or Reject Paper at Fetch Time

```python
score_paper() returns (0-100):
    if paper_type != "original_research": score = 0
    if score < 54: reject
    if year outside range: reject

Result: Saves analysis time by rejecting poor candidates early
```

### Decision Point 3: Evidence Extraction Votes to Reject Paper

```python
if dominant_paper_type in {"review", "survey", "book_chapter", "editorial"}:
    REJECT entire paper (skip analysis)

Why: No point analyzing non-original-research
```

### Decision Point 4: Skip Analyse, Do Continuous Explanation Instead

```python
if llm_intent in ("continuation", "general_question"):
    Go straight to continuous_explanation
    Don't fetch new papers

Why: User asking about existing analysis, not searching new topic
```

### Decision Point 5: Fallback Chain in Analyse Agent

```
Success: Evidence extraction → Global understanding → Comparative
Fallback 1: Evidence sparse? → Direct synthesis
Fallback 2: Direct synthesis fails? → Skeleton (minimal info)
Fallback 3: All fail? → Skip paper, continue to next
```

### Decision Point 6: PDF vs Abstract Priority

```
pdf_papers = [found_via_pdf]
abstract_papers = [found_via_abstract]

remaining = target - len(pdf_papers)
Fill remaining slots with abstracts (lower quality but better than nothing)
```

---

## Performance Characteristics

### Timeline for 3 Papers:

```
DECISION AGENT:        ~1-2 seconds
DB RETRIEVAL:          ~1-2 seconds
FETCH AGENT:           ~30-60 seconds per round (3 rounds = 90-180s)
                       + PDF downloads + parsing
ANALYSE AGENT:         ~60-120 seconds per paper (LLM calls)
                       = 3-6 minutes for 3 papers
EXPLAIN AGENT:         ~30-60 seconds (generates final review)

TOTAL: 5-10 minutes for complete analysis
```

### Token Usage:

```
Per paper analysis: ~15,000-25,000 tokens
3 papers: ~45,000-75,000 tokens
Comparative analysis: +5,000-10,000 tokens

Why high: Multi-stage pipeline, evidence + tables + context
Optimization: Batching, compression, model selection
```

### Database:

```
Chroma: ~100MB per 1000 papers (in-memory, no persistence)
SQLite: ~50MB per 1000 papers (metadata + tables)
Redis: Temporary session storage, auto-expires
```

---

## Monitoring & Debugging

### Check Agent Progress:

```
Frontend polls every 2 seconds:
GET /api/task/{task_id}
Returns: {
  "status": "running",
  "progress": [
    {"step": "decision", "state": "done"},
    {"step": "fetch", "state": "running"},  ← Current agent
    {"step": "analyse", "state": "pending"}
  ]
}
```

### Command Line Logs:

```
With flush=True:
======================================================================
DECISION AGENT RUNNING
======================================================================
DECISION MADE: FETCH_FROM_WEB
   → DB empty, fetching 3 papers from web
======================================================================

*****....*****
⏳ STARTING: 🌐 WEB_FETCH
*****....*****

[Fetch] SELECTED: [PDF] Paper Title Here...
[Fetch]  REJECTED: 'Survey Paper' (Type: survey)

======================================================================
 FINAL: 2 PAPERS SELECTED
======================================================================
   [1] paper_id_123
   [2] paper_id_456
======================================================================
```

---

## Summary: Why Each Component Exists

| Component          | Why It Exists            | Failure Mode If Missing                        |
| ------------------ | ------------------------ | ---------------------------------------------- |
| Decision Agent     | Routes to right agent    | All queries treated same, wasted LLM calls     |
| DB Retrieval       | Fast cached papers       | Every query hits web API (slow & rate limited) |
| Fetch Agent        | Scores & filters papers  | Low-quality papers analyzed, wasted time       |
| Analyse Agent      | Intelligent analysis     | Shallow paper reviews, no scoring              |
| Progress Hook      | Status tracking          | UI appears frozen, user thinks crashed         |
| Session Manager    | Remember context         | Can't ask follow-ups, state lost on crash      |
| Chroma             | Fast chunk retrieval     | Can't answer questions about papers            |
| Redis              | Multi-instance support   | Session lost if server restarts                |
| Type Voting        | Catch misclassifications | Textbooks analyzed as research                 |
| Rate Limit Handler | Resilience               | Script crashes on 429 error                    |
| Flush=True         | Visible debugging        | Logs appear only after process dies            |

---

**End of Documentation**
