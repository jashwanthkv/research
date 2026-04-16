import re
import json
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from pydantic import BaseModel
from typing import List

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool
from config import llm

from tools.semantic_search import scholar_search as semantic_scholar_search
from agents.query_rewrite import rewrite_query as rewrite_query_with_llm
from tools.tools import download_paper_pdf, parse_paper, store_paper
from vectore_store.chroma_store import add_paper_chunks
from vectore_store.paper_index_store import add_paper_to_index
from db.schema import insert_paper_chunks


class SelectInput(BaseModel):
    paper_ids: List[str]

@tool(args_schema=SelectInput)
def select(paper_ids: List[str]):
    """Select relevant paper IDs chosen by the model."""
    return {"paper_ids": paper_ids}


def generate_paper_id(paper: dict) -> str:
    base = (
        paper.get("pdf_url")
        or paper.get("link")
        or paper.get("title")
    )
    if not base:
        return None
    return "paper_" + hashlib.sha1(base.encode("utf-8")).hexdigest()



def extract_paper_year(paper: dict) -> int | None:
    """Extract publication year as int from any year-like field."""
    for field in ("year", "published_date", "date", "publicationDate"):
        raw = paper.get(field)
        if raw:
            match = re.search(r'\b(19|20)\d{2}\b', str(raw))
            if match:
                return int(match.group(0))
    return None


def is_paper_in_year_range(paper: dict, year_from: int | None, year_to: int | None) -> bool:

    if not year_from and not year_to:
        return True

    paper_year = extract_paper_year(paper)

    if paper_year is None:
        print(f"[Fetch] No year found in paper → excluded by year filter")
        return False

    if year_from and paper_year < year_from:
        return False
    if year_to and paper_year > year_to:
        return False

    return True


BLOCKED_PDF_DOMAINS = ["researchgate.net", "academia.edu"]

def is_blocked_pdf_url(url: str) -> bool:
    if not url:
        return False
    return any(domain in url for domain in BLOCKED_PDF_DOMAINS)


def get_open_access_pdf_from_s2(title: str) -> str | None:
    try:
        resp = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "fields": "openAccessPdf,externalIds", "limit": 1},
            headers={"User-Agent": "research-bot/1.0"},
            timeout=10
        )
        data = resp.json()
        papers = data.get("data", [])
        if papers:
            oa = papers[0].get("openAccessPdf")
            if oa and oa.get("url") and not is_blocked_pdf_url(oa["url"]):
                return oa["url"]
            arxiv_id = papers[0].get("externalIds", {}).get("ArXiv")
            if arxiv_id:
                return f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    except Exception as e:
        print(f"[S2 API] Error: {e}")
    return None


def extract_doi(paper: dict) -> str | None:
    doi = paper.get("doi")
    if doi:
        return doi
    match = re.search(r"10\.\d{4,}/[\w\-./:()]+", paper.get("link", ""))
    return match.group(0) if match else None


def get_pdf_from_unpaywall(doi: str, email: str = "researchbot@example.com") -> str | None:
    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}",
            params={"email": email},
            timeout=10
        )
        best = resp.json().get("best_oa_location")
        if best:
            url = best.get("url_for_pdf") or best.get("url")
            if url and not is_blocked_pdf_url(url):
                return url
    except Exception as e:
        print(f"[Unpaywall] Error: {e}")
    return None


def scrape_mdpi_pdf(page_url: str) -> str | None:
    if "mdpi.com" not in page_url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
        resp = requests.get(page_url, headers=headers, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/pdf" in href or href.endswith(".pdf"):
                full = urljoin(page_url, href)
                if "mdpi.com" in full:
                    return full
    except Exception as e:
        print(f"[MDPI Scrape] Error: {e}")
    return None


def resolve_open_access_pdf(paper: dict) -> str | None:
    pdf_url = paper.get("pdf_url")
    if pdf_url and not is_blocked_pdf_url(pdf_url):
        print("[PDF] Found via pdf_url field")
        return pdf_url

    oa = paper.get("openAccessPdf")
    if isinstance(oa, dict) and oa.get("url") and not is_blocked_pdf_url(oa["url"]):
        print("[PDF] Found via openAccessPdf field")
        return oa["url"]

    link = paper.get("link", "")
    if "arxiv.org" in link:
        match = re.search(r"arxiv\.org/(?:abs|pdf)/(\d+\.\d+)", link)
        if match:
            print("[PDF] Found via arXiv link")
            return f"https://arxiv.org/pdf/{match.group(1)}.pdf"

    if "mdpi.com" in link:
        url = scrape_mdpi_pdf(link)
        if url:
            print("[PDF] Found via MDPI scraping")
            return url

    doi = extract_doi(paper)
    if doi:
        url = get_pdf_from_unpaywall(doi)
        if url:
            print(f"[PDF] Found via Unpaywall (DOI: {doi})")
            return url

    title = paper.get("title", "")
    if title:
        url = get_open_access_pdf_from_s2(title)
        if url:
            print("[PDF] Found via Semantic Scholar API")
            return url

    return None


FETCH_SYSTEM_PROMPT = """
You are a Fetch Scoring Agent. Score how relevant a research paper is to the user's request.
Give a relevance score from 0 to 100.
Return ONLY JSON: { "score": 0-100 }
"""

def score_paper(title: str, abstract: str, user_query: str) -> int:
    clean_query = user_query.replace("title:", "").replace("Abstract:", "").split(",")[0]
    try:
        response = llm.invoke([
            SystemMessage(content=FETCH_SYSTEM_PROMPT),
            HumanMessage(content=f"User query: {clean_query}\n\nTitle: {title}\nAbstract: {abstract}")
        ])
        raw = response.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:].strip()
        return json.loads(raw).get("score", 0)
    except Exception as e:
        print(f"[Fetch] Score parse error: {e}")
        return 0


def store_paper_data(pid, title, abstract, paper, full_text, pdf_url):
    url = pdf_url or paper.get("link", "")
    store_paper({
        "paper_id":pid,
        "title":title,
        "abstract":abstract,
        "published_date":paper.get("year"),
        "url":url,
    })
    words = full_text.split()
    chunks, start, idx = [], 0, 0
    while start < len(words):
        chunks.append({"chunk_index": idx, "section": None, "content": " ".join(words[start:start + 300])})
        idx += 1
        start += 250
    insert_paper_chunks(pid, chunks)
    add_paper_chunks(pid, full_text)
    add_paper_to_index(pid, title, abstract, paper.get("year"), url=url)


MAX_PDF_ROUNDS    = 3
SEARCH_BATCH_SIZE = 20


def fetch(state):
    print("--- FETCH AGENT (SAFE, FINITE LOOP) ---")

    target         = state["max_results"]
    original_query = state["fetch_query"]
    def to_int(val):
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    year_from = to_int(state.get("year_from"))
    year_to   = to_int(state.get("year_to"))

    if year_from or year_to:
        print(f"[Fetch] 📅 Year filter: {year_from or 'any'} → {year_to or 'any'}")
    else:
        print("[Fetch] No year filter — fetching all years")

    seen_ids        = set()
    pdf_papers      = []
    abstract_papers = []

    MAX_RUNTIME = 180
    start_time  = time.time()

    optimized_query = rewrite_query_with_llm(original_query)
    print(f"[Fetch] optimized query: {optimized_query}")

    for round_num in range(1, MAX_PDF_ROUNDS + 1):

        if len(pdf_papers) >= target:
            print(f"[Fetch] ✅ PDF target reached before round {round_num}")
            break
        if time.time() - start_time > MAX_RUNTIME:
            print("[Fetch] ⏱ Time limit hit")
            break

        print(f"\n[Fetch] ══ PDF Round {round_num}/{MAX_PDF_ROUNDS} ══")

        if round_num == 1:
            round_query = optimized_query
        elif round_num == 2:
            round_query = optimized_query + " open access arxiv preprint"
        else:
            round_query = optimized_query + " survey review deep learning"

        search_results = semantic_scholar_search(round_query, SEARCH_BATCH_SIZE)
        if not search_results:
            print(f"[Fetch] Round {round_num}: no results")
            continue

        for paper in search_results:
            if len(pdf_papers) >= target:
                break
            if time.time() - start_time > MAX_RUNTIME:
                break

            pid = paper.get("paper_id") or generate_paper_id(paper)
            if pid in seen_ids:
                continue
            seen_ids.add(pid)

            title    = paper.get("title")    or ""
            abstract = paper.get("abstract") or ""
            snippet  = paper.get("snippet")  or ""

            print(f"\n[Fetch] → {title[:70]}")


            if not is_paper_in_year_range(paper, year_from, year_to):
                year = extract_paper_year(paper)
                print(f"[Fetch] Skipped (year {year} outside {year_from}–{year_to})")
                continue

            score = score_paper(title, abstract, original_query)
            print(f"[Fetch] Score: {score}")
            if score < 54:
                print("[Fetch] Skipped (low score)")
                continue

            pdf_url = resolve_open_access_pdf(paper)

            if pdf_url:
                print(f"[Fetch] Downloading: {pdf_url[:80]}...")
                pdf_path = download_paper_pdf(pdf_url, paper_id=pid)
                if pdf_path:
                    parsed    = parse_paper(pdf_path)
                    full_text = parsed.get("full_text", "") if parsed else ""
                    if full_text.strip():
                        print(f"[Fetch] ✅ PDF OK ({len(full_text.split())} words)")
                        pdf_papers.append((pid, paper, full_text, pdf_url))
                        continue
                    else:
                        print("[Fetch] PDF parsed empty")
                else:
                    print("[Fetch] PDF download failed")
            else:
                print("[Fetch] No PDF found")

            fallback = abstract or snippet
            if fallback.strip():
                abstract_papers.append((pid, paper, fallback))
                print("[Fetch] Saved as abstract fallback")

        print(f"[Fetch] Round {round_num} done → {len(pdf_papers)}/{target} PDF papers")


    remaining = target - len(pdf_papers)
    if remaining > 0:
        print(f"\n[Fetch] ══ Abstract Fallback: {remaining} slot(s) ══")
        pdf_ids = {p[0] for p in pdf_papers}
        filled  = 0
        for pid, paper, fallback_text in abstract_papers:
            if filled >= remaining:
                break
            if pid in pdf_ids or not fallback_text.strip():
                continue
            print(f"[Fetch] 📄 Abstract fallback: {paper.get('title', '')[:70]}")
            pdf_papers.append((pid, paper, fallback_text, None))
            pdf_ids.add(pid)
            filled += 1
        print(f"[Fetch] Added {filled} abstract-only paper(s)")


    print(f"\n[Fetch] ══ Storing {len(pdf_papers)} paper(s) ══")
    stored_paper_ids = []
    stored_count     = 0

    for pid, paper, full_text, pdf_url in pdf_papers:
        title    = paper.get("title")    or ""
        abstract = paper.get("abstract") or ""
        source   = "PDF" if pdf_url else "abstract"
        try:
            store_paper_data(pid, title, abstract, paper, full_text, pdf_url)
            stored_paper_ids.append(pid)
            stored_count += 1
            print(f"[Fetch] Stored [{source}]: {title[:60]}...")
        except Exception as e:
            print(f"[Fetch] Store error for {pid}: {e}")

    print(f"\n[Fetch] FINAL: {stored_count}/{target} papers stored")
    print(f"[Fetch] FINAL SELECTED PAPER IDS: {stored_paper_ids}")

    return {
        "stored_count":      stored_count,
        "has_active_papers": stored_count > 0,
        "active_paper_ids":  stored_paper_ids,
        "current_topic":     original_query,
    }