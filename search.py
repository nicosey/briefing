import json
import urllib.request
import urllib.parse

from config import SEARXNG_URL, log


def search_searxng(query, count=5, category="news", time_range="day"):
    p = {
        "q": query, "format": "json",
        "categories": category, "language": "en",
        "number_of_results": count
    }
    if time_range:
        p["time_range"] = time_range
    params = urllib.parse.urlencode(p)
    try:
        req = urllib.request.Request(f"{SEARXNG_URL}/search?{params}")
        req.add_header("User-Agent", "DailyBriefing/1.0")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            seen, unique = set(), []
            for r in data.get("results", [])[:count]:
                u = r.get("url", "")
                if u not in seen:
                    seen.add(u)
                    unique.append(r)
            return unique
    except Exception as e:
        log(f"  ⚠ Search error: {e}")
        return []


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
                    "title":   r.get("title", "").strip(),
                    "url":     r.get("url", ""),
                    "snippet": r.get("content", "").strip()[:200]
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
