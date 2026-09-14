from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ResearchMind/1.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


async def crawl_research_site(seed_url: str, max_pages: int = 8) -> list[dict]:
    """Crawl a research website, university portal, or arXiv page to extract papers and documents."""
    parsed = urlparse(seed_url)
    base_domain = parsed.netloc
    if not base_domain:
        return []

    visited: set[str] = set()
    to_visit: list[str] = [seed_url]
    discovered_sources: list[dict] = []

    async with httpx.AsyncClient(headers=HEADERS, timeout=15.0, follow_redirects=True) as client:
        while to_visit and len(visited) < max_pages:
            current_url = to_visit.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                res = await client.get(current_url)
                if res.status_code >= 400:
                    continue
                content_type = res.headers.get("content-type", "")
                if "text/html" not in content_type:
                    continue

                soup = BeautifulSoup(res.text, "html.parser")

                # Remove noise
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                    tag.decompose()

                # Extract page title
                page_title = soup.title.string.strip() if soup.title and soup.title.string else current_url

                # Check if this page itself represents a paper (e.g., arXiv, IEEE, ScienceDirect, blog)
                text = " ".join(soup.stripped_strings)
                abstract = ""
                abstract_tag = soup.find(class_=re.compile(r"abstract|summary", re.I)) or soup.find(id=re.compile(r"abstract|summary", re.I))
                if abstract_tag:
                    abstract = abstract_tag.get_text(separator=" ", strip=True)[:1000]

                # If long enough, treat current page as a discovered resource
                if len(text) > 200:
                    snippet = abstract or text[:600]
                    discovered_sources.append({
                        "title": page_title[:180],
                        "url": current_url,
                        "snippet": snippet,
                        "source_type": "academic" if ("arxiv" in current_url or "doi.org" in current_url or abstract) else "crawler",
                        "venue": base_domain,
                        "year": _extract_year(text),
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "score": 0.85 if abstract else 0.7,
                    })

                # Find candidate links on this page
                for a in soup.find_all("a", href=True):
                    href = a["href"].strip()
                    abs_url = urljoin(current_url, href)
                    parsed_link = urlparse(abs_url)

                    # Normalize
                    clean_link = abs_url.split("#")[0]
                    if not clean_link or clean_link in visited:
                        continue

                    # Direct PDF check
                    if clean_link.lower().endswith(".pdf"):
                        link_text = a.get_text(separator=" ", strip=True) or f"PDF Document from {base_domain}"
                        discovered_sources.append({
                            "title": f"[PDF] {link_text[:140]}",
                            "url": clean_link,
                            "snippet": f"Direct academic PDF resource linked from {current_url}",
                            "source_type": "crawler_pdf",
                            "venue": base_domain,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "score": 0.88,
                        })
                        continue

                    # Research keywords in link
                    link_repr = (href + " " + (a.string or "")).lower()
                    if any(k in link_repr for k in ("paper", "pub", "article", "arxiv", "pdf", "research", "abs", "doi")):
                        # Allow internal domain or arXiv
                        if parsed_link.netloc == base_domain or "arxiv.org" in parsed_link.netloc or "doi.org" in parsed_link.netloc:
                            if clean_link not in to_visit and clean_link not in visited:
                                to_visit.append(clean_link)

            except Exception:
                continue

    # Deduplicate by URL
    seen_urls = set()
    unique_sources = []
    for s in discovered_sources:
        if s["url"] not in seen_urls:
            seen_urls.add(s["url"])
            unique_sources.append(s)

    return unique_sources[:max_pages * 2]


def _extract_year(text: str) -> int | None:
    matches = re.findall(r"\b(19\d{2}|20[0-2]\d)\b", text[:1500])
    if matches:
        try:
            return int(matches[0])
        except Exception:
            return None
    return None
