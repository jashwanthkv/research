# Research Assistant Architecture & Data Flow

This document outlines the end-to-end working of the Research Assistant project, detailing the architecture, agents, RAG implementations, LLM usage, and Table RAG.

## 1. High-Level Architecture (ASCII Diagram)

```text
                      +-------------------+
                      |   User Query      |
                      +---------+---------+
                                |
                                v
                      +-------------------+
                      |   API / routes    |
                      +---------+---------+
                                |
                                v
                     +---------------------+
                     |    Agent Runner     | (Manages Session & State)
                     +---------+-----------+
                               |
                   +===========v===========+  LangGraph Workflow
                   |    Decision Agent     |
                   | (Classifies Intent)   |
                   +===========+===========+
                               |
             +-----------------+-----------------+
             |                 |                 |
             v                 v                 v
   +----------------+ +----------------+ +------------------------+
   |   Fetch Agent  | |    DB Agent    | | Continuous Explanation |
   | (Semantic Sch.)| | (Retrieve old) | | (Follow-up QA)         |
   +-------+--------+ +--------+-------+ +----------+-------------+
           |                   |                    |
           v                   |                    v
 +-------------------+         |          +--------------------+
 | PDF Download &    |         |          | Chroma Vector DB   |
 | PyMuPDF Parsing   |         |          | (paper_chunks)     |
 +---------+---------+         |          +---------+----------+
           |                   |                    |
           v                   |                    |
 +-------------------+         |                    v
 | SQLite & Chroma   | <-------+             LLM Generation
 | DB Insertion      |
 +---------+---------+
           |
           v
 +-------------------+
 |   Analyse Agent   | (Multi-Stage Reasoning & Table RAG)
 +---------+---------+
           |
           v
 +-------------------+
 |   Explain Agent   | (Human-readable summary)
 +---------+---------+
           |
           v
    FINAL RESPONSE
```

## 2. Core Components & Agents

The system is orchestrated using a **LangGraph** state machine. State is persisted in-memory (`_SESSION_STORE`) and via Redis.

### 2.1 Decision Agent
- **Role:** The entry point for the graph.
- **Function:** Uses the LLM to classify the user's intent. Determines if the user is asking for new papers (`fetch`), looking up existing papers in DB (`retrieve`), or asking follow-up questions on active papers (`continuation`).
- **Output:** Next step routing instructions.

### 2.2 Fetch Agent
- **Role:** Gathers research data from the web.
- **Function:**
  1. Rewrites user query into optimized search terms.
  2. Queries Semantic Scholar API.
  3. Uses LLM to score paper relevance.
  4. Scrapes Open-Access PDFs (arXiv, MDPI, etc.).
  5. Parses PDFs into raw text using PyMuPDF and extracts Markdown tables.
  6. Splits text into manageable "chunks" (300 words with 50-word overlap).
  7. Populates SQLite (papers, chunks, tables) and ChromaDB (vectors).

### 2.3 Analyse Agent (The Reasoning Engine)
- **Role:** Deep analysis of the retrieved text and tables.
- **Function (4-Stage Pipeline):**
  1. **Evidence Extraction:** Batches chunks and extracts atomic claims and evidence.
  2. **Global Understanding:** Merges evidence and performs **Table RAG** (injecting Markdown tables into the prompt) to produce a holistic evaluation (novelty, methodology, metrics).
  3. **Research Critique:** Assigns quantitative scores (1-5) and formulates strengths/weaknesses.
  4. **Cross-Paper Comparison:** Analyases trends across all fetched papers to provide a synthesis of the field.

### 2.4 Explain Agent
- **Role:** Formats the deep JSON analysis into user-friendly Markdown.
- **Function:** Generates the final UI-ready text, summarizing methodologies, key contributions, and drawbacks.

### 2.5 Continuous Explanation Agent
- **Role:** Handles follow-up conversational QA.
- **Function:** When the user asks a follow-up, it performs a **Vector RAG** search against ChromaDB using the `active_paper_ids` to retrieve the exact chunks containing the answer.

---

## 3. Data Flow & Databases

The system strategically partitions data across SQLite and ChromaDB to balance structured retrieval and semantic search.

### SQLite (Structured & Persistent)
- **`papers` table:** Stores metadata, raw full text, and BLOB vectors of titles/abstracts.
- **`paper_chunks` table:** Stores ordered 300-word chunks. Used by the Analyse Agent to read the paper sequentially.
- **`paper_tables` table:** Stores extracted tables as Markdown. Used for Table RAG.

### ChromaDB (Semantic Vector Search)
- **`paper_chunks` collection:** Stores chunk embeddings. **Used exclusively by Continuous Explanation Agent** for semantic RAG on follow-up questions. Re-initialized per session.
- **`paper_index` collection:** Stores paper metadata and a combined "title+abstract" embedding. Used for fast metadata lookups and to check if a topic has already been researched recently.

---

## 4. LLM Usage & Pydantic Validation

- **Provider:** Groq Cloud APIs (High-speed inference).
- **Structured Output:** Almost all agents (Analyse, Fetch scoring, Decision) enforce strict schema generation using `pydantic` models (e.g., `EvidenceExtraction`, `GlobalUnderstanding`).
- **Rate-Limiting:** Implements exponential backoff (`_invoke_with_retry`) to handle Groq API 429 Rate Limit errors gracefully.

---

## 5. RAG Implementations

### Standard Text RAG (Vector RAG)
Implemented in the **Continuous Explanation Agent**.
1. User asks a follow-up ("What dataset was used?").
2. Query is converted to an embedding.
3. Cosine similarity search runs against the `paper_chunks` Chroma collection.
4. Top-K chunks are injected into the LLM prompt context to answer the question.

### Table RAG
Implemented in the **Analyse Agent**.
1. During PDF parsing, tabular data is extracted and converted to Markdown format.
2. Tables are stored in the SQLite `paper_tables` table.
3. In Stage 2 (Global Understanding), the `get_paper_tables()` function fetches up to 5 tables for the paper.
4. The raw Markdown tables are injected directly into the LLM prompt alongside the extracted text evidence. This ensures the LLM has exact experimental metrics and baseline comparisons that are often lost in standard text chunking.
