import ssl
import sys
import os
import urllib.request
from datetime import datetime

ssl._create_default_https_context = ssl._create_unverified_context

from config import (
    SEARXNG_URL, OLLAMA_URL,
    log, load_topic_config
)
from db        import (init_db, save_run, save_output, add_to_outbox,
                       find_recent_runs, find_recent_tweets, mark_aggregated,
                       get_collections, get_last_run_timestamp)
from search    import fetch_all_results, mock_fetch_results
from ai        import generate_output, mock_output
from format    import build_raw_briefing, build_output_message


def persist_results(timestamp, topic, raw_briefing, generated_outputs, outputs_cfg, cfg,
                    default_dest, aggregated_from=None):
    agg_timestamps = [ts for ts, _ in (aggregated_from or [])]
    save_run(timestamp, topic, raw_briefing, aggregated_from=agg_timestamps)

    for output_cfg in outputs_cfg:
        output_type = output_cfg["type"]
        name        = output_cfg.get("name", output_type)
        content     = generated_outputs.get(output_type)
        if not content:
            continue
        output_id = save_output(timestamp, output_type, name, content)
        message   = build_output_message(content, output_cfg, cfg)
        out_dest  = output_cfg.get("dest", default_dest)
        for dest in [d.strip() for d in out_dest.split(",") if d.strip()]:
            add_to_outbox(output_id, dest, message)

    # write files
    safe_ts = timestamp.replace(":", "-").replace("T", "_")
    folder  = os.path.join("output", f"{safe_ts}_{topic}")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "raw_briefing.txt"), "w") as f:
        f.write(raw_briefing)
    for output_cfg in outputs_cfg:
        output_type = output_cfg["type"]
        content     = generated_outputs.get(output_type)
        if content:
            with open(os.path.join(folder, f"{output_type}.txt"), "w") as f:
                f.write(build_output_message(content, output_cfg, cfg))
    log(f"  💾 Files: {folder}/")


def main():
    raw_args = sys.argv[1:]
    mock          = "--mock"     in raw_args
    dry_run       = "--dry-run"  in raw_args
    full_day      = "--full-day" in raw_args

    lookback      = 0
    briefing_type = None
    for i, a in enumerate(raw_args):
        if a == "--lookback" and i + 1 < len(raw_args):
            try:
                lookback = int(raw_args[i + 1])
            except ValueError:
                pass
        if a == "--briefing-type" and i + 1 < len(raw_args):
            briefing_type = raw_args[i + 1]

    args = []
    skip_next = False
    for a in raw_args:
        if skip_next:
            skip_next = False
            continue
        if a in ("--lookback", "--briefing-type"):
            skip_next = True
            continue
        if a.startswith("--"):
            continue
        args.append(a)

    if not args:
        available = [f[:-5] for f in os.listdir("config") if f.endswith(".json")]
        print("Usage: python briefing.py <topic> [--mock] [--dry-run] [--lookback N]")
        print("  --mock        fake SearXNG + Ollama (no services needed)")
        print("  --dry-run     skip DB write and outbox, print to terminal instead")
        print("  --lookback N  include last N minutes of saved summaries as AI context")
        print(f"Available topics: {', '.join(sorted(available))}")
        print("Run publish.py to deliver queued outputs.")
        sys.exit(1)

    topic = args[0]
    cfg   = load_topic_config(topic)

    # Apply briefing type overrides (title + AI instruction)
    if briefing_type:
        bt = cfg.get("briefing_types", {}).get(briefing_type)
        if bt:
            cfg["briefing_title"]       = bt.get("title", cfg["ai_topic"])
            cfg["briefing_instruction"] = bt.get("ai_instruction", "")
        else:
            log(f"⚠ Unknown briefing type '{briefing_type}' — using defaults")

    if lookback == 0:
        lookback = cfg.get("lookback_minutes", 0)

    # Default to narrative-only if config has no outputs defined
    outputs_cfg = cfg.get("outputs", [
        {"type": "narrative", "name": cfg.get("ai_topic", "Daily Digest")}
    ])

    default_dest = os.environ.get("BRIEFING_DEST", "console")
    timestamp    = datetime.now().isoformat(timespec="seconds")

    log("=" * 40)
    log(cfg["title"]
        + (" [MOCK]"                  if mock              else "")
        + (" [DRY RUN]"               if dry_run           else "")
        + (" [FULL DAY]"              if full_day          else "")
        + (f" [LOOKBACK {lookback}m]" if lookback          else ""))
    log("=" * 40)

    if not dry_run:
        init_db()

    # Determine data source: collected results from DB, or live search
    results_data = None
    using_collections = False

    if mock:
        log("⚠  Mock mode — using mock search results")
        ollama_available = True
    else:
        # Try to use hourly-collected data if available
        if not dry_run:
            if full_day:
                # Look back to midnight today for end-of-day summary
                since = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
                log(f"📦 Full-day mode — loading collections since midnight...")
            else:
                last_run = get_last_run_timestamp(topic)
                since = last_run or datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat(timespec="seconds")
                log(f"📦 Loading collections since {since[:16]}...")

            collected = get_collections(topic, since)
            if collected:
                results_data = collected
                using_collections = True
                total = sum(len(s["results"]) for s in results_data)
                log(f"  ✅ {len(results_data)} sections, {total} articles from collected data")
            else:
                log("  ℹ No collections found — falling back to live search")

        if not using_collections:
            try:
                req = urllib.request.Request(f"{SEARXNG_URL}/search?q=test&format=json")
                req.add_header("User-Agent", "DailyBriefing/1.0")
                urllib.request.urlopen(req, timeout=10)
                log("✅ SearXNG: OK")
            except Exception:
                log("❌ SearXNG not reachable")
                sys.exit(1)

        try:
            urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
            log("✅ Ollama: OK")
            ollama_available = True
        except Exception:
            log("⚠ Ollama not reachable — will skip AI outputs")
            ollama_available = False

    log("")

    previous_narratives = []
    if lookback and not dry_run:
        previous_narratives = find_recent_runs(topic, lookback)
        if previous_narratives:
            log(f"📚 Found {len(previous_narratives)} previous summary(s) to aggregate")
        else:
            log("📚 No recent summaries found — starting fresh")
        log("")

    if results_data is None:
        log("📡 Fetching search results...")
        results_data = mock_fetch_results(cfg["searches"]) if mock else fetch_all_results(cfg["searches"])
        log("")

    raw_briefing = build_raw_briefing(results_data, cfg)
    log(f"📋 Raw briefing: {len(raw_briefing)} chars")
    log("")

    generated_outputs = {}

    for output_cfg in outputs_cfg:
        output_type = output_cfg["type"]
        name        = output_cfg.get("name", output_type)

        log(f"🧠 Generating {name}...")
        if mock:
            content = mock_output(output_cfg, cfg)
        elif ollama_available:
            if output_type == "narrative":
                prev = previous_narratives
            elif output_type == "tweet" and not dry_run:
                lookback_hours = output_cfg.get("tweet_lookback_hours", 6)
                prev = find_recent_tweets(topic, lookback_hours * 60)
            else:
                prev = None
            content = generate_output(output_cfg, results_data, cfg, prev)
        else:
            content = None

        if content:
            generated_outputs[output_type] = content
            out_dest = output_cfg.get("dest", default_dest)
            log(f"  ✅ {name} ({len(content)} chars) → queued for {out_dest}")
        else:
            log(f"  ⚠ Skipping {name}")
        log("")

    if not dry_run:
        log("💾 Saving results...")
        persist_results(timestamp, topic, raw_briefing, generated_outputs, outputs_cfg, cfg,
                        default_dest, aggregated_from=previous_narratives or None)
        if previous_narratives:
            mark_aggregated([ts for ts, _ in previous_narratives])
            log(f"  ✅ Marked {len(previous_narratives)} previous run(s) as aggregated")

    log("")
    log("Done!")


if __name__ == "__main__":
    main()
