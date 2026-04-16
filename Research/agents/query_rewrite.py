import json
import re
from config import llm

INVALID_PATTERN = re.compile(
    r"\b(AND|OR|NOT)\b|\d+|[()\[\]{}]",
    re.IGNORECASE
)
QUERY_REWRITE_SYSTEM_PROMPT = """
You are an academic search query generator.

Convert the user request into a search-engine-style query
as used in Google Scholar or OpenAlex.

STRICT RULES:
- Extract ONLY noun phrases and technical terms
- REMOVE verbs, intent, actions, questions
- REMOVE numbers, counts, and instructions
- Keep domain-specific terminology
- Use space-separated keywords
- Use "quoted phrases" for multi-word technical concepts
- NO explanations
- Output ONLY valid JSON

Return format:
{
  "query": "keyword1 \"multi word technical phrase\" keyword2"
}
"""


def normalize_query(text: str) -> str:
    """
    Structural cleanup only — NO semantic guessing.
    """
    text = INVALID_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def rewrite_query(user_query: str, max_retries: int = 2) -> str:
    for attempt in range(max_retries):
        try:
            response = llm.invoke([
                {"role": "system", "content": QUERY_REWRITE_SYSTEM_PROMPT},
                {"role": "user", "content": user_query}
            ])

            raw = (response.content or "").strip()
            raw = re.sub(r"```json|```", "", raw).strip()

            if not raw:
                raise ValueError("Empty LLM output")

            data = json.loads(raw)
            query = data.get("query", "").strip()

            if not query:
                raise ValueError("Empty query field")

            return normalize_query(query)

        except Exception as e:
            print(f"[QueryRewrite] Attempt {attempt + 1} failed: {e}")

    # Final fallback: remove numbers & structure only
    return normalize_query(user_query)
