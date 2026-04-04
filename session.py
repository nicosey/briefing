"""
Live session runner.

Runs collect + brief at regular intervals, saving each mini-briefing to the DB.
At the end (or on Ctrl+C), runs a final aggregation pass that synthesises all
interim briefings into a single output and publishes it.

Usage:
  python3 session.py <topic> [options]

Options:
  --interval N       Minutes between interim cycles (default: 60)
  --count N          Number of interim cycles before the final run (default: 3)
  --duration N       Total session duration in minutes (alternative to --count)
  --briefing-type T  Briefing type for the final aggregated output
  --mock             Use mock data — no SearXNG or Ollama needed
  --dry-run          Skip DB writes and delivery (useful for testing the loop)

Examples:
  # 3 cycles every 10 min, then aggregate
  python3 session.py robotics --interval 10 --count 3

  # Run for 2 hours, collecting every 30 min, end-of-day final summary
  python3 session.py uk_capital_markets --duration 120 --interval 30 --briefing-type eod
"""
import os
import sys
import subprocess
import time
from datetime import datetime, timedelta

from config import log, load_topic_config


def _run(script, args):
    cmd = ["python3", script] + args
    log(f"  ▶ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    raw_args = sys.argv[1:]
    mock     = "--mock"    in raw_args
    dry_run  = "--dry-run" in raw_args

    interval      = 60
    count         = None
    duration      = None
    briefing_type = None

    skip_next = False
    topic_args = []
    for i, a in enumerate(raw_args):
        if skip_next:
            skip_next = False
            continue
        if a == "--interval" and i + 1 < len(raw_args):
            interval = int(raw_args[i + 1]); skip_next = True
        elif a == "--count" and i + 1 < len(raw_args):
            count = int(raw_args[i + 1]); skip_next = True
        elif a == "--duration" and i + 1 < len(raw_args):
            duration = int(raw_args[i + 1]); skip_next = True
        elif a == "--briefing-type" and i + 1 < len(raw_args):
            briefing_type = raw_args[i + 1]; skip_next = True
        elif not a.startswith("--"):
            topic_args.append(a)

    if not topic_args:
        print(__doc__)
        sys.exit(1)

    topic = topic_args[0]
    load_topic_config(topic)  # validate topic exists early

    if count is None and duration is not None:
        count = max(1, duration // interval)
    elif count is None:
        count = 3

    # Lookback covers the full session plus a small buffer
    lookback = count * interval + interval

    flags      = (["--mock"] if mock else []) + (["--dry-run"] if dry_run else [])
    final_type = (["--briefing-type", briefing_type] if briefing_type else [])

    log("=" * 40)
    log(f"SESSION: {topic}")
    log(f"  {count} cycle(s) × {interval} min interval → final aggregation")
    if briefing_type:
        log(f"  Final briefing type: {briefing_type}")
    log("=" * 40)
    log("")

    completed = 0
    try:
        for i in range(count):
            log(f"── Cycle {i + 1}/{count} ({datetime.now().strftime('%H:%M')}) ──")
            _run("collect.py", [topic] + flags)
            _run("briefing.py", [topic, "--save-only"] + flags)
            completed += 1

            if i < count - 1:
                next_at = datetime.now() + timedelta(minutes=interval)
                log(f"  ⏱  Next cycle at {next_at.strftime('%H:%M')} — sleeping {interval} min...")
                log("")
                time.sleep(interval * 60)

    except KeyboardInterrupt:
        log("")
        log("⚠  Interrupted — running final aggregation on completed cycles...")

    if completed == 0:
        log("No cycles completed — nothing to aggregate.")
        sys.exit(0)

    log("")
    log(f"── Final aggregation ({completed} cycle(s), lookback {lookback} min) ──")
    ok = _run("briefing.py", [topic, "--lookback", str(lookback)] + final_type + flags)
    if ok and not dry_run:
        _run("publish.py", [])

    log("")
    log("Session complete.")


if __name__ == "__main__":
    main()
