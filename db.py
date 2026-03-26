import sqlite3
import json
import os
from datetime import datetime

from config import DB_PATH, log


DB_TIMEOUT = 30  # seconds to wait before raising "locked" error


def _connect():
    return sqlite3.connect(DB_PATH, timeout=DB_TIMEOUT)


def _db_op(fn):
    """Wrap a DB operation with a clear locked-error message."""
    try:
        return fn()
    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            log("❌ DB locked — another briefing run is writing. Try again in a moment.")
        else:
            log(f"❌ DB error: {e}")
        raise


def init_db():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    def _():
        con = _connect()
        con.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                timestamp       TEXT PRIMARY KEY,
                topic           TEXT NOT NULL,
                raw_briefing    TEXT,
                aggregated_from TEXT DEFAULT '[]',
                aggregated      INTEGER DEFAULT 0
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS outputs (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_timestamp TEXT NOT NULL,
                output_type   TEXT NOT NULL,
                name          TEXT NOT NULL,
                content       TEXT,
                FOREIGN KEY(run_timestamp) REFERENCES runs(timestamp)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                output_id    INTEGER NOT NULL,
                dest         TEXT NOT NULL,
                message      TEXT NOT NULL,
                created_at   TEXT NOT NULL,
                published_at TEXT,
                FOREIGN KEY(output_id) REFERENCES outputs(id)
            )
        """)
        con.commit()
        con.close()
    _db_op(_)


def save_run(timestamp, topic, raw_briefing, aggregated_from=None):
    def _():
        con = _connect()
        con.execute(
            "INSERT OR REPLACE INTO runs "
            "(timestamp, topic, raw_briefing, aggregated_from) "
            "VALUES (?, ?, ?, ?)",
            (timestamp, topic, raw_briefing, json.dumps(aggregated_from or []))
        )
        con.commit()
        con.close()
        log(f"  🗄  DB: saved run {timestamp}")
    _db_op(_)


def save_output(run_timestamp, output_type, name, content):
    """Save an output and return its inserted id."""
    def _():
        con = _connect()
        cur = con.execute(
            "INSERT INTO outputs (run_timestamp, output_type, name, content) "
            "VALUES (?, ?, ?, ?)",
            (run_timestamp, output_type, name, content)
        )
        output_id = cur.lastrowid
        con.commit()
        con.close()
        log(f"  🗄  DB: saved {output_type} output for {run_timestamp}")
        return output_id
    return _db_op(_)


def add_to_outbox(output_id, dest, message):
    def _():
        con = _connect()
        con.execute(
            "INSERT INTO outbox (output_id, dest, message, created_at) "
            "VALUES (?, ?, ?, ?)",
            (output_id, dest, message, datetime.now().isoformat(timespec="seconds"))
        )
        con.commit()
        con.close()
        log(f"  📬 Outbox: queued for {dest}")
    _db_op(_)


def get_pending_outbox(dest=None):
    """Return [(outbox_id, dest, message)] for unpublished entries."""
    def _():
        con = _connect()
        if dest:
            rows = con.execute(
                "SELECT id, dest, message FROM outbox "
                "WHERE published_at IS NULL AND dest=? "
                "ORDER BY created_at",
                (dest,)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, dest, message FROM outbox "
                "WHERE published_at IS NULL "
                "ORDER BY created_at"
            ).fetchall()
        con.close()
        return rows
    return _db_op(_)


def mark_outbox_published(outbox_id):
    def _():
        con = _connect()
        con.execute(
            "UPDATE outbox SET published_at=? WHERE id=?",
            (datetime.now().isoformat(timespec="seconds"), outbox_id)
        )
        con.commit()
        con.close()
    _db_op(_)


def find_recent_runs(topic, lookback_minutes):
    """Return [(timestamp, narrative_content)] for recent runs in chronological order.

    Uses the outputs table (type='narrative'). Stops as soon as it hits a run
    that already aggregated its predecessors — no need to look further back.
    """
    cutoff = datetime.fromtimestamp(
        datetime.now().timestamp() - lookback_minutes * 60
    ).isoformat()

    def _():
        con = _connect()
        rows = con.execute(
            "SELECT r.timestamp, o.content, r.aggregated_from "
            "FROM runs r "
            "JOIN outputs o ON o.run_timestamp = r.timestamp "
            "WHERE r.topic=? AND r.timestamp>=? AND o.output_type='narrative' "
            "ORDER BY r.timestamp DESC",
            (topic, cutoff)
        ).fetchall()
        con.close()
        return rows

    rows = _db_op(_)
    found = []
    for ts, content, agg_from in rows:
        found.append((ts, content))
        if json.loads(agg_from):  # this run already pulled in predecessors
            break

    return list(reversed(found))  # chronological order


def mark_aggregated(timestamps):
    def _():
        con = _connect()
        con.executemany(
            "UPDATE runs SET aggregated=1 WHERE timestamp=?",
            [(ts,) for ts in timestamps]
        )
        con.commit()
        con.close()
    _db_op(_)
