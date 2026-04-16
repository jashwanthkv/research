import requests
from tools.tools import download_paper_pdf

def reconstruct_abstract(inv):
    if not inv:
        return ""
    words = sorted(
        ((pos, word) for word, positions in inv.items() for pos in positions)
    )
    return " ".join(w for _, w in words)

def extract_pdf_url(w):
    # 1️⃣ Open access URL
    oa = w.get("open_access") or {}
    if oa.get("oa_url"):
        return oa["oa_url"]

    # 2️⃣ Primary location PDF
    loc = w.get("primary_location") or {}
    if loc.get("pdf_url"):
        return loc["pdf_url"]

    return None


import time
import requests

import requests


def scholar_search(query, k=10):
    url = "https://google.serper.dev/scholar"
    headers = {
        "X-API-KEY": "701d3d7ee5ee69a16f0a54d43a9e81b8d8c9b3e1",
        "Content-Type": "application/json"
    }

    payload = {
        "q": query,
        "num": k
    }

    r = requests.post(url, headers=headers, json=payload)
    r.raise_for_status()

    results = []
    for item in r.json().get("organic", []):
        results.append({
            "title": item.get("title"),
            "pdf_url": item.get("pdfUrl"),
            "link": item.get("link"),
            "snippet": item.get("snippet")
        })

    return results


# print(openalex_search("machine learning in healthcare", max_results=3))