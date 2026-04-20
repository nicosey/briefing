import json
import urllib.request
import urllib.parse

from config import SEARXNG_URL, log


PAGE_SIZE = 10  # SearXNG returns ~10 results per page


def _search_page(query, category, time_range, pageno):
    """Fetch a single page of SearXNG results."""
    p = {
        "q": query, "format": "json",
        "categories": category, "language": "en",
        "pageno": pageno,
    }
    if time_range:
        p["time_range"] = time_range
    params = urllib.parse.urlencode(p)
    req = urllib.request.Request(f"{SEARXNG_URL}/search?{params}")
    req.add_header("User-Agent", "DailyBriefing/1.0")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
        return data.get("results", [])


def search_searxng(query, count=5, category="news", time_range="day"):
    """Search SearXNG, paginating automatically if count > PAGE_SIZE."""
    seen, unique = set(), []
    page = 1
    try:
        while len(unique) < count:
            results = _search_page(query, category, time_range, page)
            if not results:
                break
            new = 0
            for r in results:
                if len(unique) >= count:
                    break
                u = r.get("url", "")
                if u and u not in seen:
                    seen.add(u)
                    unique.append(r)
                    new += 1
            if new == 0:
                break  # no new results on this page — stop
            page += 1
    except Exception as e:
        log(f"  ⚠ Search error: {e}")
    return unique


def fetch_all_results(searches):
    all_results = []
    for s in searches:
        log(f"  Searching: {s['title']}...")
        results = search_searxng(s["query"], s.get("count", 5), s.get("category", "news"), s.get("time_range", "day"))
        all_results.append({
            "section": s["title"],
            "emoji":   s["emoji"],
            "results": [
                {
                    "title":     r.get("title", "").strip(),
                    "url":       r.get("url", ""),
                    "snippet":   r.get("content", "").strip()[:200],
                    "published": r.get("publishedDate", "")
                }
                for r in results
            ]
        })
    return all_results


def mock_fetch_results(searches):
    """Fake search results — no SearXNG needed."""
    results = []
    for s in searches:
        results.append({
            "section": s["title"],
            "emoji":   s["emoji"],
            "results": [
                {
                    "title":   f"[MOCK] Sample headline for {s['title']} #{i+1}",
                    "url":     f"https://example.com/{s['title'].lower().replace(' ', '-')}-{i+1}",
                    "snippet": f"Mock snippet for the {s['title']} section, item {i+1}. "
                               "Used for local testing without SearXNG running."
                }
                for i in range(s.get("count", 3))
            ]
        })
    return results
