import json
from config import llm

SYSTEM_PROMPT = """You are a Research Explanation Agent.

You explain research papers clearly to the user.
Papers can be technical (ML, engineering, medicine) OR non-technical (sociology, qualitative research, case studies, surveys, humanities).

YOUR ONLY JOB: Explain what is actually IN each paper based on the data provided.

For EACH paper:
1. Title
2. Year
3. Link
4. Main Idea       — what is this paper about, what question does it address?
5. Methodology     — how did the researchers do their work?
                     (experiments / interviews / surveys / case studies / content analysis / etc.)
6. Key Contribution — what does this paper add or find that is useful?
7. Drawbacks       — what are the weaknesses or limitations?

Then write an OVERALL SUMMARY.

RULES:
- Explain only what the data says — do not invent
- For non-technical papers: explain themes, findings, participant groups, research context
- For technical papers: explain algorithms, architectures, metrics, results
- If a field has content → expand on it clearly
- If a field is empty → write 1-2 sentences based on the title and available fields
- Never write "Not explicitly stated" or "Not available" — always give the reader something useful
- Length should match the depth of available content — don't pad, don't cut short
"""


def explain(state):
    print("---EXPLAIN AGENT---")

    analysis   = state.get("analysis")
    user_query = state.get("userQuery", "")
    goal       = state.get("goal", "")

    if not analysis:
        return {"explanation": "No analysis was available to explain."}

    paper_analyses = analysis.get("paper_analyses", [])
    overall_trends = analysis.get("overall_trends", {})

    if not paper_analyses:
        return {"explanation": "No papers were analysed."}

    prompt = f"""User Query: {user_query}

=== PAPER ANALYSES ===
{json.dumps(paper_analyses, indent=2, ensure_ascii=False)}

=== OVERALL TRENDS ===
{json.dumps(overall_trends, indent=2, ensure_ascii=False)}

Write a detailed explanation for EACH paper using sections:
1. Title / 2. Year / 3. Link / 4. Main Idea / 5. Methodology / 6. Key Contribution / 7. Drawbacks

Then write OVERALL SUMMARY.

Use the content from the JSON above. Expand meaningfully on each field.
For non-technical papers: focus on the research context, who was studied, what was found, and why it matters.
For technical papers: focus on the approach, architecture, results, and novelty.
"""

    response = llm.invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt}
    ])

    return {"explanation": response.content}