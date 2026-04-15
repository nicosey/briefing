"""
Hourly news collector.
Runs SearXNG searches for a topic and saves raw results to the DB.
The briefing scripts read these collections instead of running searches themselves.

Usage: python collect.py <topic> [--mock]
"""
import ssl
import sys
import urllib.request

ssl._create_default_https_context = ssl._create_unverified_context

from config import SEARXNG_URL, log, load_topic_config
from db import init_db, save_collection, archive_collections
from search import fetch_all_results, mock_fetch_results


def main():
    raw_args = sys.argv[1:]
    mock = "--mock" in raw_args
    args = [a for a in raw_args if not a.startswith("--")]

    if not args:
        import os
        available = [f[:-5] for f in os.listdir("config") if f.endswith(".json")]
        print("Usage: python collect.py <topic> [--mock]")
        print(f"Available topics: {', '.join(sorted(available))}")
        sys.exit(1)

    topic = args[0]
    cfg   = load_topic_config(topic)

    log("=" * 40)
    log(f"📡 Collecting: {cfg['title']}" + (" [MOCK]" if mock else ""))
    log("=" * 40)

    if not mock:
        try:
            req = urllib.request.Request(f"{SEARXNG_URL}/search?q=test&format=json")
            req.add_header("User-Agent", "DailyBriefing/1.0")
            urllib.request.urlopen(req, timeout=10)
            log("✅ SearXNG: OK")
        except Exception:
            log("❌ SearXNG not reachable")
            sys.exit(1)

    log("")
    log("🔍 Fetching search results...")
    results = mock_fetch_results(cfg["searches"]) if mock else fetch_all_results(cfg["searches"])
    log("")

    init_db()
    save_collection(topic, results)
    archive_collections(max_age_hours=48)

    log("")
    log("Done!")


if __name__ == "__main__":
    main()
