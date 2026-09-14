from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:12000]


async def fetch_url(url: str) -> dict:
    if not url.startswith("http"):
        return {"url": url, "ok": False, "text": "", "error": "invalid url"}
    headers = {
        "User-Agent": "ResearchMind/1.0 (academic research assistant; local mini-project)"
    }
    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True, headers=headers) as client:
            res = await client.get(url)
            ctype = res.headers.get("content-type", "")
            if "pdf" in ctype.lower():
                return {"url": str(res.url), "ok": True, "text": "", "error": "", "is_pdf": True, "bytes": res.content}
            text = html_to_text(res.text)
            return {"url": str(res.url), "ok": True, "text": text, "error": "", "is_pdf": False}
    except Exception as exc:
        return {"url": url, "ok": False, "text": "", "error": str(exc)}
