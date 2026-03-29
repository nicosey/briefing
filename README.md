# briefing

A lightweight daily news briefing pipeline. Searches for recent news via [SearXNG](https://github.com/searxng/searxng), generates AI outputs via [Ollama](https://ollama.com), saves to SQLite, and publishes to Telegram.

## How it works

1. **Collect** (`collect.py`) — runs hourly, searches SearXNG and saves raw results to SQLite. No AI, no delivery.
2. **Briefing** (`briefing.py`) — runs at scheduled times (e.g. 7am, 12pm, 5pm), reads collected data, generates AI outputs, queues them in the outbox.
3. **Publish** (`publish.py`) — reads the outbox and delivers queued messages to Telegram.

`run.sh` wraps steps 2 and 3 together for launchd. `collect.sh` wraps step 1.

Separating collection from generation means each briefing draws on several hours of accumulated news rather than a single search snapshot.

### Briefing types

Each run can be given a `--briefing-type` that changes both the message title and the AI's writing instruction:

| Type | Title | AI instruction |
| --- | --- | --- |
| `morning` | Morning Start | Set the scene for the trading day ahead |
| `midday` | Mid Day Update | Summarise how markets have developed through the morning |
| `eod` | End of Day Summary | Wrap up the full trading day |

Types are configured per topic in the JSON config under `briefing_types`.

### Full-day mode

The `--full-day` flag tells the briefing to use all collections since midnight rather than just since the last briefing. Used for the end-of-day run so it covers the complete trading day.

## Requirements

- Python 3.8+
- [SearXNG](https://github.com/searxng/searxng) running locally
- [Ollama](https://ollama.com) running locally with a model pulled
- For Telegram delivery: a bot token and chat ID

No third-party Python packages required — uses only the standard library.

## Setup

```bash
cp .env.example .env
# edit .env with your values
```

### .env

```ini
SEARXNG_URL=http://localhost:8888
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3-coder:30b

# Telegram (optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id

# Default outbox destination for outputs without an explicit dest (default: console)
BRIEFING_DEST=telegram
```

## Usage

```bash
# Collect latest news for a topic (run hourly)
python collect.py <topic>

# Generate a briefing from collected data and queue for delivery
python briefing.py <topic> [options]

# Publish all queued outputs to Telegram
python publish.py

# Or run briefing + publish together
./run.sh <topic> [briefing flags...]
```

### collect.py options

| Option | Description |
| --- | --- |
| `--mock` | Fake SearXNG — no services needed |

### briefing.py options

| Option | Description |
| --- | --- |
| `--mock` | Fake SearXNG + Ollama — no services needed |
| `--dry-run` | Skip DB write and outbox, print to terminal instead |
| `--briefing-type <name>` | Set the briefing type (e.g. `morning`, `midday`, `eod`) — controls title and AI instruction |
| `--full-day` | Use all collections since midnight (for end-of-day summary) |
| `--lookback N` | Include last N minutes of saved narratives as AI context |

### Examples

```bash
# Test locally with no services
python briefing.py robotics --mock --dry-run

# Real run using collected data
python briefing.py uk_capital_markets --briefing-type morning

# End of day summary covering all day's collections
python briefing.py uk_capital_markets --briefing-type eod --full-day

# Collect + brief + publish in one step
./run.sh uk_capital_markets --briefing-type morning
```

**Available topics:** `robotics`, `uk_capital_markets`, `data_centres`, `bjj`

## Delivery destinations

| Destination | Description |
| --- | --- |
| `console` | Print to terminal |
| `telegram` | Send to a Telegram chat via bot API |

Set `BRIEFING_DEST` in `.env` as the default, or set `dest` per output in the topic config:

```json
"outputs": [
  {"type": "narrative", "name": "Daily Digest",  "dest": "telegram"},
  {"type": "tweet",     "name": "Tweet Summary", "dest": "telegram"}
]
```

## Output types

Each topic config defines an `outputs` array controlling what the AI generates per run:

```json
"outputs": [
  {"type": "narrative", "name": "Daily Digest",  "max_words": 500},
  {"type": "tweet",     "name": "Tweet Summary", "max_chars": 280, "tweet_lookback_hours": 6}
]
```

| Type | Description |
| --- | --- |
| `narrative` | 3–4 paragraph analysis, up to `max_words` |
| `tweet` | Single breaking-news sentence, up to `max_chars`. Looks back at recent tweets to avoid repeating the same story |

**Tweet deduplication:** `tweet_lookback_hours` (default: 6) controls how far back the AI looks when avoiding repeated stories.

**Latest news focus:** Name a search section with "latest" in the title (e.g. `LATEST UK CAPITAL MARKETS NEWS`) and the tweet prompt draws exclusively from that section.

## Adding a topic

Create a JSON file in `config/`:

```json
{
  "title": "My Briefing",
  "header_emoji": "📋",
  "footer_emoji": "🔍",
  "ai_persona": "an analyst writing a daily briefing",
  "ai_topic": "Today's Update",
  "lookback_minutes": 120,
  "briefing_types": {
    "morning": {
      "title": "Morning Start",
      "ai_instruction": "Set the scene for the day ahead."
    },
    "midday": {
      "title": "Mid Day Update",
      "ai_instruction": "Summarise how things have developed through the morning."
    },
    "eod": {
      "title": "End of Day Summary",
      "ai_instruction": "Wrap up the full day's key developments."
    }
  },
  "outputs": [
    {"type": "narrative", "name": "Daily Digest",  "max_words": 500, "dest": "telegram"},
    {"type": "tweet",     "name": "Tweet Summary", "max_chars": 280, "dest": "telegram", "tweet_lookback_hours": 6}
  ],
  "searches": [
    {"emoji": "📰", "title": "LATEST MY TOPIC NEWS", "query": "my topic news today", "count": 5, "category": "news"},
    {"emoji": "📊", "title": "SECTION NAME",          "query": "your search query",  "count": 4, "category": "news"}
  ]
}
```

Then test:

```bash
python collect.py my_topic --mock
python briefing.py my_topic --briefing-type morning --mock --dry-run
```

## Database

Results are stored in `output/briefings.db` (SQLite — no server required):

| Table | Contents |
| --- | --- |
| `collections` | Raw search results saved by collect.py — one row per hourly run per topic. Cleaned up after 48 hours. |
| `runs` | One row per briefing run: topic, timestamp, raw headlines, aggregation state |
| `outputs` | One row per AI output per run: type, name, content — kept permanently |
| `outbox` | Delivery queue: one row per output×destination. Undelivered entries are retried on every publish run. Published entries older than 24 hours are cleaned up automatically. |

## Scheduling on macOS (launchd)

Four jobs for the UK capital markets topic:

| Job | Schedule | Command |
| --- | --- | --- |
| `com.briefing.uk_capital_markets_collect` | Hourly 7am–5pm | `collect.sh uk_capital_markets` |
| `com.briefing.uk_capital_markets` | 7am daily | `run.sh uk_capital_markets --briefing-type morning` |
| `com.briefing.uk_capital_markets_digest` | 12pm daily | `run.sh uk_capital_markets --briefing-type midday` |
| `com.briefing.uk_capital_markets_eod` | 5pm daily | `run.sh uk_capital_markets --briefing-type eod --full-day` |

### Plist template

Save as `~/Library/LaunchAgents/com.briefing.LABEL.plist`, replacing `YOUR_USER`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefing.LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/projects/briefing/run.sh</string>
        <string>TOPIC</string>
        <string>--briefing-type</string>
        <string>morning</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>7</integer>
        <key>Minute</key><integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/LABEL.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/LABEL.error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

### Load and test

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.briefing.LABEL.plist
launchctl list | grep briefing
launchctl start com.briefing.LABEL
tail -f ~/projects/briefing/output/LABEL.log
```

### Notes

- launchd runs jobs as your user, so credentials in `.env` are picked up normally
- If the machine is asleep at the scheduled time, the job is skipped — it does not catch up on wake
- publish.py is safe to run independently at any time; it skips already-published outbox entries
- To clear stale outbox entries: `sqlite3 output/briefings.db "UPDATE outbox SET published_at=datetime('now') WHERE published_at IS NULL;"`

## Output structure

```text
output/
  briefings.db                          # SQLite — all collections, runs, outputs, and outbox
  2026-03-29_07-00-00_uk_capital_markets/
    raw_briefing.txt                    # formatted headlines (HTML)
    narrative.txt                       # AI narrative output
    tweet.txt                           # AI tweet output
```
