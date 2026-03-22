import urllib.request
import urllib.parse
import json
import sqlite3
import ssl
import sys
import os
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

# ============================================================
# CONFIG — loaded from .env + topic JSON
# ============================================================

def _load_env(path=".env"):
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass

_load_env()

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")
SEARXNG_URL        = os.environ.get("SEARXNG_URL", "http://localhost:8888")
OLLAMA_URL         = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL       = os.environ.get("OLLAMA_MODEL", "qwen3-coder:30b")
DB_PATH            = os.environ.get("BRIEFING_DB", os.path.join("output", "briefings.db"))


def load_topic_config(topic_arg):
    if os.path.isfile(topic_arg):
        path = topic_arg
    else:
        path = os.path.join("config", f"{topic_arg}.json")
    if not os.path.isfile(path):
        available = [f[:-5] for f in os.listdir("config") if f.endswith(".json")]
        print(f"Error: config not found: {path}")
        print(f"Available topics: {', '.join(sorted(available))}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


# ============================================================
# LOGGING
# ============================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


# ============================================================
# DELIVERY
# ============================================================

class Delivery:
    """Base class for briefing delivery destinations."""

    def send(self, message):
        raise NotImplementedError

    def send_long(self, message):
        """Send a message that may exceed the destination's size limit.
        Default: single send. Override if chunking is needed."""
        self.send(message)


class TelegramDelivery(Delivery):
    MAX_CHARS = 4000

    def __init__(self, token, chat_id):
        self.token   = token
        self.chat_id = chat_id

    def send(self, message):
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = json.dumps({
            "chat_id": self.chat_id, "text": message,
            "parse_mode": "HTML", "disable_web_page_preview": True
        }).encode("utf-8")
        try:
            req = urllib.request.Request(url, data=payload)
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
                if result.get("ok"):
                    log("  ✅ Telegram: sent")
                    return True
                log(f"  ❌ Telegram error: {result}")
                return False
        except Exception as e:
            log(f"  ❌ Telegram send failed: {e}")
            return False

    def send_long(self, message):
        if len(message) <= self.MAX_CHARS:
            return self.send(message)
        chunks = message.split("\n\n")
        current = ""
        for chunk in chunks:
            if len(current) + len(chunk) + 2 > self.MAX_CHARS:
                if current:
                    self.send(current)
                current = chunk
            else:
                current = current + "\n\n" + chunk if current else chunk
        if current:
            self.send(current)


class ConsoleDelivery(Delivery):
    """Prints to stdout — used for --dry-run."""

    def send(self, message):
        print(message)


# Registry: name -> factory function
# To add a new destination, add an entry here and implement the class above.
DELIVERY_REGISTRY = {
    "telegram": lambda: TelegramDelivery(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID),
    "console":  lambda: ConsoleDelivery(),
}


def get_delivery(dry_run):
    if dry_run:
        return ConsoleDelivery()
    dest = os.environ.get("BRIEFING_DEST", "telegram")
    if dest not in DELIVERY_REGISTRY:
        log(f"❌ Unknown delivery destination: {dest}. Choose from: {', '.join(DELIVERY_REGISTRY)}")
        sys.exit(1)
    return DELIVERY_REGISTRY[dest]()


# ============================================================
# SEARCH
# ============================================================

def search_searxng(query, count=5, category="news"):
    params = urllib.parse.urlencode({
        "q": query, "format": "json",
        "categories": category, "language": "en",
        "number_of_results": count
    })
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
        results = search_searxng(s["query"], s.get("count", 5), s.get("category", "news"))
        all_results.append({
            "section": s["title"],
            "emoji": s["emoji"],
            "results": [
                {
                    "title": r.get("title", "").strip(),
                    "url":   r.get("url", ""),
                    "snippet": r.get("content", "").strip()[:200]
                }
                for r in results
            ]
        })
    return all_results


# ============================================================
# DATABASE
# ============================================================
#
# Schema: runs(timestamp PK, topic, raw_briefing, narrative,
#              aggregated_from JSON, aggregated bool)
#
# timestamp is an ISO-format string — e.g. "2026-03-22T09:00:01"
# It acts as a natural, human-readable primary key.

def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            timestamp       TEXT PRIMARY KEY,
            topic           TEXT NOT NULL,
            raw_briefing    TEXT,
            narrative       TEXT,
            aggregated_from TEXT DEFAULT '[]',
            aggregated      INTEGER DEFAULT 0
        )
    """)
    con.commit()
    con.close()


def db_save_run(timestamp, topic, raw_briefing, narrative, aggregated_from=None):
    con = sqlite3.connect(DB_PATH)
    con.execute(
        "INSERT OR REPLACE INTO runs "
        "(timestamp, topic, raw_briefing, narrative, aggregated_from) "
        "VALUES (?, ?, ?, ?, ?)",
        (timestamp, topic, raw_briefing, narrative, json.dumps(aggregated_from or []))
    )
    con.commit()
    con.close()
    log(f"  🗄  DB: saved run {timestamp}")


def db_find_recent_runs(topic, lookback_minutes):
    """Return [(timestamp, narrative)] for recent runs, newest-first scan.

    Stops as soon as it hits a run that already aggregated its predecessors —
    no need to look further back than that.
    Returns results in chronological order.
    """
    cutoff = datetime.fromtimestamp(
        datetime.now().timestamp() - lookback_minutes * 60
    ).isoformat()

    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT timestamp, narrative, aggregated_from FROM runs "
        "WHERE topic=? AND timestamp>=? AND narrative IS NOT NULL "
        "ORDER BY timestamp DESC",
        (topic, cutoff)
    ).fetchall()
    con.close()

    found = []
    for ts, narrative, agg_from in rows:
        found.append((ts, narrative))
        if json.loads(agg_from):   # this run already pulled in predecessors
            break

    return list(reversed(found))  # chronological order


def db_mark_aggregated(timestamps):
    con = sqlite3.connect(DB_PATH)
    con.executemany(
        "UPDATE runs SET aggregated=1 WHERE timestamp=?",
        [(ts,) for ts in timestamps]
    )
    con.commit()
    con.close()


# ============================================================
# AI NARRATIVE
# ============================================================

def generate_narrative(results_data, cfg, previous_narratives=None):
    results_text = ""
    for section in results_data:
        results_text += f"\n{section['section']}:\n"
        for r in section["results"]:
            results_text += f"- {r['title']}"
            if r["snippet"]:
                results_text += f": {r['snippet']}"
            results_text += "\n"

    history_block = ""
    if previous_narratives:
        history_block = "\nPREVIOUS SUMMARIES (for context and trend continuity):\n"
        for ts, text in previous_narratives:
            history_block += f"\n[{ts[:16].replace('T', ' ')}]\n{text}\n"
        history_block += "\n---\n"

    agg_instruction = (
        "- Where relevant, note how today's news continues or diverges from the previous summaries above\n"
        if previous_narratives else ""
    )

    prompt = f"""/no_think
You are {cfg['ai_persona']}.
Based on today's news below, write a concise, engaging narrative summary called "{cfg['ai_topic']}".

Rules:
- Write 3-4 short paragraphs maximum
- Lead with the most important story
- Mention key companies and deals
- Add brief analysis on what trends you see
- Keep it under 500 words
- Write in a professional but accessible tone
- Do NOT use markdown formatting, just plain text
- End with one sentence on what to watch next
{agg_instruction}
{history_block}TODAY'S RAW NEWS DATA:
{results_text}

Write the narrative now:"""

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4000}
    }).encode("utf-8")

    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode())
            content = data.get("message", {}).get("content", "").strip()
            if content:
                log(f"  ✅ AI narrative: {len(content)} chars")
                return content
            log("  ⚠ AI returned empty response")
            return None
    except Exception as e:
        log(f"  ⚠ AI narrative failed: {e}")
        return None


# ============================================================
# FORMAT
# ============================================================

def truncate(text, max_len=120):
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def build_raw_briefing(results_data, cfg):
    now = datetime.now()
    header = (
        f'{cfg["header_emoji"]} <b>{cfg["title"].upper()}</b>\n'
        f'📅 {now.strftime("%A, %d %B %Y")} • {now.strftime("%H:%M")}\n'
        f'{"─" * 30}'
    )
    sections = [header]
    for s in results_data:
        section = f'\n{s["emoji"]} <b>{s["section"]}</b>\n'
        if s["results"]:
            for r in s["results"]:
                section += f'• <b>{r["title"]}</b>'
                if r["snippet"]:
                    section += f'\n  <i>{truncate(r["snippet"])}</i>'
                if r["url"]:
                    section += f'\n  <a href="{r["url"]}">→ Read</a>'
                section += "\n"
        else:
            section += "  <i>No results found today</i>\n"
        sections.append(section)
    sections.append(f'\n{"─" * 30}\n{cfg["footer_emoji"]} <i>SearXNG • {len(results_data)} searches</i>')
    return "\n".join(sections)


def build_narrative_message(narrative, cfg):
    now = datetime.now()
    return (
        f'{cfg["header_emoji"]} <b>{cfg["ai_topic"].upper()}</b>\n'
        f'📅 {now.strftime("%A, %d %B %Y")}\n'
        f'{"─" * 30}\n\n'
        f'{narrative}\n\n'
        f'{"─" * 30}\n'
        f'🧠 <i>Written by {OLLAMA_MODEL}</i>'
    )


# ============================================================
# MOCK
# ============================================================

def mock_fetch_results(searches):
    results = []
    for s in searches:
        results.append({
            "section": s["title"],
            "emoji": s["emoji"],
            "results": [
                {
                    "title": f"[MOCK] Sample headline for {s['title']} #{i+1}",
                    "url": f"https://example.com/{s['title'].lower().replace(' ', '-')}-{i+1}",
                    "snippet": f"Mock snippet for the {s['title']} section, item {i+1}. "
                               "Used for local testing without SearXNG running."
                }
                for i in range(s.get("count", 3))
            ]
        })
    return results


def mock_narrative(cfg):
    return (
        f"[MOCK NARRATIVE] This is a test narrative for {cfg['ai_topic']}. "
        "In a real run, Ollama would generate several paragraphs of analysis here. "
        "The formatting, delivery, and message splitting are all exercised in mock mode.\n\n"
        "A second paragraph would discuss trends and key players. "
        "This confirms the full pipeline is working end-to-end on your laptop.\n\n"
        "Watch for real data when you run this on the Mac Mini."
    )


# ============================================================
# SAVE
# ============================================================

def save_results(timestamp, topic, raw_briefing, narrative, cfg, aggregated_from=None):
    # — DB (primary) —
    agg_timestamps = [ts for ts, _ in (aggregated_from or [])]
    db_save_run(timestamp, topic, raw_briefing, narrative, aggregated_from=agg_timestamps)

    # — Files (human-readable archive) —
    safe_ts = timestamp.replace(":", "-").replace("T", "_")
    folder  = os.path.join("output", f"{safe_ts}_{topic}")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "raw_briefing.txt"), "w") as f:
        f.write(raw_briefing)
    if narrative:
        with open(os.path.join(folder, "narrative.txt"), "w") as f:
            f.write(build_narrative_message(narrative, cfg))
    log(f"  💾 Files: {folder}/")


# ============================================================
# MAIN
# ============================================================

def main():
    raw_args = sys.argv[1:]
    mock    = "--mock"    in raw_args
    dry_run = "--dry-run" in raw_args
    save    = "--save"    in raw_args

    lookback = 0
    for i, a in enumerate(raw_args):
        if a == "--lookback" and i + 1 < len(raw_args):
            try:
                lookback = int(raw_args[i + 1])
            except ValueError:
                pass

    args = []
    skip_next = False
    for a in raw_args:
        if skip_next:
            skip_next = False
            continue
        if a == "--lookback":
            skip_next = True
            continue
        if a.startswith("--"):
            continue
        args.append(a)

    if not args:
        available = [f[:-5] for f in os.listdir("config") if f.endswith(".json")]
        print("Usage: python briefing.py <topic> [--mock] [--dry-run] [--save] [--lookback N]")
        print("  --mock        fake SearXNG + Ollama (no services needed)")
        print("  --dry-run     skip delivery, print to terminal instead")
        print("  --save        write results to output/<timestamp>_<topic>/")
        print("  --lookback N  include last N minutes of saved summaries as AI context")
        print(f"Available topics: {', '.join(sorted(available))}")
        print(f"Delivery destinations: {', '.join(DELIVERY_REGISTRY)} (set BRIEFING_DEST in .env)")
        sys.exit(1)

    topic = args[0]
    cfg   = load_topic_config(topic)

    if lookback == 0:
        lookback = cfg.get("lookback_minutes", 0)

    delivery = get_delivery(dry_run)
    dest_name = "console" if dry_run else os.environ.get("BRIEFING_DEST", "telegram")

    log("=" * 40)
    log(cfg["title"]
        + (" [MOCK]"          if mock              else "")
        + (f" [{dest_name.upper()}]")
        + (" [SAVE]"          if save              else "")
        + (f" [LOOKBACK {lookback}m]" if lookback and save else ""))
    log("=" * 40)

    if not dry_run and not mock and dest_name == "telegram" and TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        log("❌ Set TELEGRAM_BOT_TOKEN in .env")
        sys.exit(1)

    if mock:
        log("⚠  Mock mode — skipping SearXNG and Ollama")
        ollama_available = True
    else:
        try:
            req = urllib.request.Request(f"{SEARXNG_URL}/search?q=test&format=json")
            req.add_header("User-Agent", "DailyBriefing/1.0")
            urllib.request.urlopen(req, timeout=10)
            log("✅ SearXNG: OK")
        except:
            log("❌ SearXNG not reachable")
            sys.exit(1)

        try:
            urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
            log("✅ Ollama: OK")
            ollama_available = True
        except:
            log("⚠ Ollama not reachable — will skip AI narrative")
            ollama_available = False

    log("")

    if save:
        init_db()

    previous_narratives = []
    if lookback and save:
        previous_narratives = db_find_recent_runs(topic, lookback)
        if previous_narratives:
            log(f"📚 Found {len(previous_narratives)} previous summary(s) to aggregate")
        else:
            log("📚 No recent summaries found — starting fresh")
    log("")

    log("📡 Fetching search results...")
    results_data = mock_fetch_results(cfg["searches"]) if mock else fetch_all_results(cfg["searches"])
    log("")

    log("📨 Sending raw briefing...")
    raw_briefing = build_raw_briefing(results_data, cfg)
    log(f"  Raw briefing: {len(raw_briefing)} chars")
    delivery.send_long(raw_briefing)
    log("")

    log("🧠 Generating AI narrative...")
    if mock:
        narrative = mock_narrative(cfg)
    elif ollama_available:
        narrative = generate_narrative(results_data, cfg, previous_narratives or None)
    else:
        narrative = None

    if narrative:
        story = build_narrative_message(narrative, cfg)
        log("📨 Sending AI story...")
        delivery.send_long(story)
    else:
        log("⚠ Skipping AI narrative")

    if save:
        log("💾 Saving results...")
        timestamp = datetime.now().isoformat(timespec="seconds")
        save_results(timestamp, topic, raw_briefing, narrative, cfg,
                     aggregated_from=previous_narratives or None)
        if previous_narratives:
            db_mark_aggregated([ts for ts, _ in previous_narratives])
            log(f"  ✅ Marked {len(previous_narratives)} previous run(s) as aggregated")

    log("")
    log("Done!")


if __name__ == "__main__":
    main()
