import sqlite3
import json
import os
from datetime import datetime

from config import DB_PATH, log


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


def save_run(timestamp, topic, raw_briefing, narrative, aggregated_from=None):
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


def find_recent_runs(topic, lookback_minutes):
    """Return [(timestamp, narrative)] for recent runs in chronological order.

    Scans newest-first and stops as soon as it hits a run that already
    aggregated its predecessors — no need to look further back.
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


def mark_aggregated(timestamps):
    con = sqlite3.connect(DB_PATH)
    con.executemany(
        "UPDATE runs SET aggregated=1 WHERE timestamp=?",
        [(ts,) for ts in timestamps]
    )
    con.commit()
    con.close()
