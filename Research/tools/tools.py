
import arxiv
import requests
import os
import fitz
import sqlite3
import numpy as np
import json
from typing import Optional, List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.tools import tool
from vectore_store.chroma_store import resolve_papers
from vectore_store.paper_index_store import query_paper_index

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import embeddings
from langchain_community.vectorstores import FAISS

DB_PATH = "db/knowledge.db"

from datetime import datetime

def search_papers(
    query: str,
    max_results: int = 6,
    years_limit: int = 6,
    arxiv_categories: Optional[List[str]] = None
):
    """
    Search arXiv for recent papers only.
    Filters papers older than `years_limit`.
    Optionally constrains by arXiv categories.
    """

    current_year = datetime.now().year

    # 🔹 Build category filter if provided
    category_filter = ""
    if arxiv_categories:
        category_filter = " OR ".join([f"cat:{c}" for c in arxiv_categories])
        query = f"({query}) AND ({category_filter})"

    client = arxiv.Client()

    search = arxiv.Search(
        query=query,
        max_results=max_results * 3,  # fetch more, filter later
        sort_by=arxiv.SortCriterion.SubmittedDate
    )

    results = []

    for paper in client.results(search):
        if not paper.published:
            continue

        paper_year = paper.published.year
        if current_year - paper_year > years_limit:
            continue  #  skip old papers

        results.append({
            "paper_id": paper.entry_id.split("/")[-1],
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "published": paper.published.strftime("%Y-%m-%d"),
            "year": paper_year,
            "abstract": paper.summary,
            "pdf_url": paper.pdf_url
        })

        if len(results) >= max_results:
            break

    return results

import os
from curl_cffi import requests
from urllib.parse import urlparse

import os
from curl_cffi import requests
from urllib.parse import urlparse

def download_paper_pdf(
    pdf_url: str,
    paper_id: str,
    save_dir: str = "data/pdfs"
):
    if not pdf_url or not paper_id:
        return None

    os.makedirs(save_dir, exist_ok=True)

    # 🔑 Use paper_id as filename (safe + unique)
    safe_id = paper_id.replace("/", "_").replace(":", "_")
    file_name = f"{safe_id}.pdf"
    file_path = os.path.join(save_dir, file_name)

    if os.path.exists(file_path):
        return file_path

    try:
        response = requests.get(
            pdf_url,
            impersonate="chrome120",
            timeout=30,
            allow_redirects=True
        )
        response.raise_for_status()

        with open(file_path, "wb") as f:
            f.write(response.content)

        return file_path

    except Exception as e:
        print(f"[Download ERROR] {pdf_url}: {e}")
        return None

def parse_paper(pdf_path: str):
    """
    Extract text + tables from PDF and return structured sections.
    Tables are extracted via PyMuPDF's find_tables() and returned as markdown.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return {}

    try:
        doc = fitz.open(pdf_path)
        full_text = ""
        tables_markdown = []

        for page_num, page in enumerate(doc):
            full_text += page.get_text()

            # ── Table extraction via PyMuPDF ──
            try:
                tabs = page.find_tables()
                if tabs.tables:
                    for i, table in enumerate(tabs.tables):
                        try:
                            md = table.to_markdown()
                            if md and len(md.strip()) > 20:  # skip tiny/empty tables
                                tables_markdown.append({
                                    "page": page_num + 1,
                                    "table_index": i,
                                    "markdown": md
                                })
                        except Exception:
                            pass  # skip malformed tables
            except Exception:
                pass  # find_tables may fail on some pages

        doc.close()
        if tables_markdown:
            print(f"[PDF] Extracted {len(tables_markdown)} table(s)")
    except Exception as e:
        print(f"Error parsing PDF {pdf_path}: {e}")
        return {}

    text_lower = full_text.lower()

    def extract_section(start, end_list):
        if start not in text_lower:
            return ""
        s = text_lower.index(start)
        e = len(text_lower)
        
        # dynamic search for nearest end marker
        found_ends = []
        for end_marker in end_list:
            if end_marker in text_lower and text_lower.index(end_marker) > s:
                found_ends.append(text_lower.index(end_marker))
        
        if found_ends:
            e = min(found_ends)
            
        return full_text[s:e].strip()

    # Heuristic section extraction
    return {
        "abstract": extract_section("abstract", ["introduction", "1. introduction"]),
        "methodology": extract_section("method", ["result", "conclusion"]),
        "results": extract_section("result", ["conclusion", "references"]),
        "full_text": full_text,  # full paper — analyser handles its own budget
        "tables": tables_markdown  # NEW: extracted tables as markdown
    }

def embed_text(text: str):
    return embeddings.embed_query(text)

def serialize_vector(vector):
    return np.array(vector, dtype=np.float32).tobytes()

def deserialize_vector(blob):
    return np.frombuffer(blob, dtype=np.float32)


def search_db_similarity(query: str, top_k: int = 10, search_field: str = "abstract"):
    """
    Compute cosine similarity against all stored vectors in DB.
    search_field can be 'abstract' or 'title'.
    """
    query_vector = embed_text(query)
    
    conn = get_connection()
    cursor = conn.cursor()
    
    # Select ID, title, and the target vector
    if search_field == "title":
         cursor.execute("SELECT paper_id, title, title_vector, published_date FROM papers")
    else:
         cursor.execute("SELECT paper_id, title, abstract_vector, published_date FROM papers")
         
    rows = cursor.fetchall()
    conn.close()
    
    scored_papers = []
    
    for r in rows:
        pid, title, blob, date = r
        if not blob:
            continue
        vec = deserialize_vector(blob)
        # Cosine similarity
        score = np.dot(query_vector, vec) / (np.linalg.norm(query_vector) * np.linalg.norm(vec))
        scored_papers.append({
            "paper_id": pid,
            "title": title,
            "published_date": date,
            "score": score
        })
        
    scored_papers.sort(key=lambda x: x["score"], reverse=True)
    return scored_papers[:top_k]

def get_paper_details(paper_ids: list):
    if not paper_ids:
        return []
    conn = get_connection()
    cursor = conn.cursor()
    
    placeholders = ",".join("?" for _ in paper_ids)
    query = f"""
        SELECT paper_id, title, abstract, methodology, results, full_text, published_date
        FROM papers
        WHERE paper_id IN ({placeholders})
    """
    
    cursor.execute(query, paper_ids)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "paper_id": r[0],
            "title": r[1],
            "abstract": r[2],
            "methodology": r[3],
            "results": r[4],
            "full_text": r[5],
            "published_date": r[6]
        })
    return results

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)
def store_paper(paper: dict) -> dict:
    """
    Store a parsed paper into SQLite + vectors.
    Accepts both 'url'/'pdf_url' and 'published'/'published_date' field names.
    """
    conn = get_connection()
    cur = conn.cursor()

    title_vec = embed_text(paper["title"])
    abs_vec   = embed_text(paper.get("abstract", ""))

    # ── Normalise field names ──
    url  = paper.get("url") or paper.get("pdf_url") or ""
    date = paper.get("published_date") or paper.get("published") or ""

    cur.execute("""
        INSERT OR REPLACE INTO papers
        (paper_id, title, abstract, published_date, url,
         methodology, results, full_text, title_vector, abstract_vector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        paper["paper_id"],
        paper["title"],
        paper.get("abstract", ""),
        date,
        url,
        paper.get("methodology", ""),
        paper.get("results", ""),
        paper.get("full_text", ""),
        serialize_vector(title_vec),
        serialize_vector(abs_vec)
    ))

    conn.commit()
    conn.close()

    return {"status": "stored", "paper_id": paper["paper_id"]}
import sqlite3



def get_paper_details(paper_ids):
    """
    Fetch full paper records from SQLite using paper_ids.
    """

    if not paper_ids:
        return []

    conn = get_connection()
    cur = conn.cursor()

    placeholders = ",".join("?" for _ in paper_ids)

    query = f"""
        SELECT
            paper_id,
            title,
            abstract,
            published_date,
            url,
            methodology,
            results,
            full_text
        FROM papers
        WHERE paper_id IN ({placeholders})
    """

    cur.execute(query, paper_ids)
    rows = cur.fetchall()

    conn.close()

    papers = []
    for row in rows:
        papers.append({
            "paper_id": row[0],
            "title": row[1],
            "abstract": row[2],
            "published": row[3],
            "url": row[4],
            "methodology": row[5],
            "results": row[6],
            "full_text": row[7],
        })

    return papers
def get_paper_chunks_by_paper_id(paper_id: str):
    """
    Fetch all chunks for a given paper_id from SQLite.
    Ordered by chunk_index to preserve flow.
    """

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            chunk_index,
            section,
            content
        FROM paper_chunks
        WHERE paper_id = ?
        ORDER BY chunk_index ASC
    """, (paper_id,))

    rows = cur.fetchall()
    conn.close()

    chunks = []
    for row in rows:
        chunks.append({
            "chunk_index": row[0],
            "section": row[1],
            "content": row[2]
        })

    return chunks


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Drop old table if exists to ensure schema update
    cursor.execute("DROP TABLE IF EXISTS papers")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS papers (
            paper_id TEXT PRIMARY KEY,
            title TEXT,
            abstract TEXT,
            published_date TEXT,
            url TEXT,
            methodology TEXT,
            results TEXT,
            full_text TEXT,
            title_vector BLOB,
            abstract_vector BLOB,
            stored_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

  # YOU already have DB logic

@tool
def resolve(query: str):
    """
    Resolve which stored papers are relevant to the user query.
    Uses vector search + DB fetch.
    """

    paper_ids = resolve_papers(query)

    if not paper_ids:
        return {"resolved_papers": []}

    papers = get_paper_details(paper_ids)

    return {
        "resolved_papers": papers
    }


# if __name__ == "__main__":
#     init_db()

# tools/decision_tools.py




@tool
def retrieve_similar_papers(query: str, top_k: int = 5):
    """
    Retrieve freshness info of stored papers for decision making.
    """

    metas = query_paper_index(query, top_k=top_k)

    years = [m.get("year") for m in metas if m.get("year")]

    return {
        "years": years,
        "count": len(years)
    }
