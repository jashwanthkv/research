import json
from config import llm

SYSTEM_PROMPT = """You are a senior research scientist writing a researcher-grade paper review.
Your analysis should read like an internal review at Google DeepMind — specific, evidence-based, and actionable.

For EACH paper in the input, write a structured review covering these sections IN ORDER:

1. **Title** — exact paper title
2. **Year** — publication year
3. **Link** — paper URL
4. **Paper Type** — original research / review / survey / book chapter / editorial
   If non-research, state this clearly and keep brief.

5. **Core Research Question** — What specific problem/gap does this paper address?
   BAD: "This paper explores NLP and AI."
   GOOD: "This paper addresses the O(n²) memory bottleneck in Transformer self-attention for documents >4096 tokens."

6. **Novelty Assessment** — What is genuinely new? Why does it matter vs prior work?
   Name the specific technique introduced and what makes it different.

7. **Methodology** — EXACT technical approach:
   - Model/architecture with specific names
   - Datasets with names and sizes
   - Training setup: optimizer, LR, batch size, hardware, epochs
   - Evaluation metrics and baselines
   - For non-technical: study design, N=, demographics, analytical framework

8. **Key Results** — Present the most important quantitative/qualitative findings.
   Include any tables from the paper data. Format results as a table when possible:
   | Metric | Value | vs Baseline |
   Present ablation study findings if available.

9. **Experimental Strength** — What was done well experimentally?

10. **Weaknesses & Missing Baselines** — Specific, actionable:
    - Missing baselines (name them)
    - Untested domains
    - Scalability concerns with numbers
    - Methodological gaps

11. **Assumptions & Scalability** — What assumptions are made? Are they realistic?
    Will this work at scale? Evidence-based assessment.

12. **Reproducibility** — Can this be reproduced? What details are missing?

13. **Reviewer Verdict** — If critique data is available:
    - Show scores (Novelty, Technical Correctness, Experimental Quality, etc.)
    - State overall recommendation (accept/reject/borderline)
    - List key strengths and weaknesses

14. **Research Impact** — How significant is this contribution to the field?

Then write a **CROSS-PAPER ANALYSIS** section if comparative data is available:
- Methodology comparison table
- Novelty ranking
- Research gaps across all papers
- Practical recommendation
- Field evolution trajectory

RULES:
- Ground every statement in evidence from the analysis data
- EVERY sentence must contain a CONCRETE DETAIL — no filler
- If tables are provided, embed them directly in your explanation
- For non-research papers: note this briefly and summarize scope
- Never write "Not explicitly stated" — give what you have concretely
- Present critique scores visually: "⭐⭐⭐⭐☆ (4/5)" format
"""


def explain(state):
    print("\n" + "="*70)
    print("EXPLANATION AGENT RUNNING")
    print("="*70)

    analysis   = state.get("analysis")
    user_query = state.get("userQuery", "")
    goal       = state.get("goal", "")

    if not analysis:
        print(" No analysis available to explain")
        print("="*70 + "\n")
        return {"explanation": "No analysis was available to explain."}

    paper_analyses = analysis.get("paper_analyses", [])
    overall_trends = analysis.get("overall_trends", {})

    if not paper_analyses:
        print(" No papers analyzed")
        print("="*70 + "\n")
        return {"explanation": "No papers were analysed."}

    print(f" Generating review for {len(paper_analyses)} paper(s)")
    print("="*70)

    # Build a rich prompt with all new research-grade data
    prompt = f"""User Query: {user_query}

=== PAPER ANALYSES ({len(paper_analyses)} papers) ===
{json.dumps(paper_analyses, indent=2, ensure_ascii=False)}

=== CROSS-PAPER ANALYSIS ===
{json.dumps(overall_trends, indent=2, ensure_ascii=False)}

Write a detailed, researcher-grade review for EACH paper using the sections specified.
Include ALL research-grade fields: novelty, experimental strength, weaknesses, assumptions,
scalability, reproducibility, key results, critique scores, and tables.

For papers with critique data, present the reviewer verdict with star ratings.
For papers with table data, embed the tables in the appropriate sections.

Then write the CROSS-PAPER ANALYSIS if comparative data is available:
- Methodology comparison as a formatted table
- Novelty ranking
- Research gaps
- Practical recommendation
- Field evolution

Extract and highlight every specific detail from the JSON above.
Do NOT write generic summaries. Every sentence must contain concrete, evidence-based detail.
"""

    import time as _time
    for attempt in range(3):
        try:
            response = llm.invoke([
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt}
            ])
            print(f"\nExplanation generated successfully ({len(response.content)} characters)")
            print("="*70 + "\n")
            return {"explanation": response.content}
        except Exception as e:
            if "429" in str(e) or "rate_limit" in str(e).lower():
                wait = 15 * (attempt + 1)
                print(f"[Explain] Rate limit hit. Waiting {wait}s... (attempt {attempt + 1}/3)")
                _time.sleep(wait)
            else:
                print(f"[Explain] Error: {e}")
                print("="*70 + "\n")
                return {"explanation": f"Error generating explanation: {e}"}

    print(" Rate limit exceeded")
    print("="*70 + "\n")
    return {"explanation": "Rate limit exceeded. Please try again in a few minutes."}