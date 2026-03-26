# briefing

A lightweight daily news briefing pipeline. Searches for recent news via [SearXNG](https://github.com/searxng/searxng), generates AI outputs via [Ollama](https://ollama.com), saves to SQLite, and publishes to Telegram and/or X.

## How it works

1. **Search** — runs a set of queries against a local SearXNG instance
2. **Generate** — feeds the results to a local Ollama model to produce each configured output (e.g. narrative, tweet)
3. **Save** — stores results in SQLite + a timestamped folder under `output/`, and queues outputs in an outbox per destination
4. **Publish** — a separate `publish.py` script reads the outbox and delivers to each destination (Telegram, X, console)
5. **Aggregate** *(optional)* — injects recent saved summaries as context so the AI can track trends across runs

## Requirements

- Python 3.8+
- [SearXNG](https://github.com/searxng/searxng) running locally
- [Ollama](https://ollama.com) running locally with a model pulled
- For Telegram delivery: a bot token and chat ID
- For X delivery: `pip install playwright && playwright install chromium`, plus X credentials

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

# X / Twitter (optional)
X_USERNAME=your_username
X_PASSWORD=your_password

# Default outbox destination for outputs without an explicit dest (default: console)
BRIEFING_DEST=telegram
```

## Usage

```bash
# Generate, save to DB, and queue outputs in outbox
python briefing.py <topic> [options]

# Publish all queued outputs
python publish.py

# Publish to a specific destination only
python publish.py telegram
python publish.py x
```

### briefing.py options

| Option | Description |
| --- | --- |
| `--mock` | Fake SearXNG + Ollama — no services needed |
| `--dry-run` | Skip DB write and outbox, print to terminal instead |
| `--lookback N` | Include last N minutes of saved summaries as AI context |

### Examples

```bash
# Test locally with no services
python briefing.py robotics --mock --dry-run

# Real run
python briefing.py robotics

# Real run with trend aggregation from the last 2 hours
python briefing.py robotics --lookback 120

# Generate then publish
python briefing.py robotics && python publish.py
```

**Available topics:** `robotics`, `uk_capital_markets`, `data_centres`, `bjj`

## Delivery destinations

| Destination | Description |
| --- | --- |
| `console` | Print to terminal |
| `telegram` | Send to a Telegram chat via bot API |
| `x` | Post to X via Playwright browser automation |

Set `BRIEFING_DEST` in `.env` as the default, or set `dest` per output in the topic config:

```json
"outputs": [
  {"type": "narrative", "name": "Daily Digest",  "dest": "telegram"},
  {"type": "tweet",     "name": "Tweet Summary", "dest": "x"}
]
```

Comma-separate to send one output to multiple destinations: `"dest": "telegram,x"`.

## Output types

Each topic config defines an `outputs` array controlling what the AI generates per run:

```json
"outputs": [
  {"type": "narrative", "name": "Daily Digest",  "max_words": 500},
  {"type": "tweet",     "name": "Tweet Summary", "max_chars": 280}
]
```

| Type | Description |
| --- | --- |
| `narrative` | 3–4 paragraph analysis, up to `max_words` |
| `tweet` | Single breaking-news sentence, up to `max_chars`. If the config has a search section with "latest" in the title, the tweet is drawn from that section only — keeping it focused on the most recent stories |

To add a new output type: add a prompt builder to `ai.py`, a formatter to `format.py`, and an entry in the config.

## Aggregation

When `--lookback` is set, each run:

- Queries the SQLite DB for recent `narrative` outputs of the same topic
- Injects them into the AI prompt so it can note continuity and divergence
- Marks those prior runs as aggregated so they aren't re-used unnecessarily

The lookback window can also be set per-topic in the config JSON:

```json
"lookback_minutes": 120
```

## Database

Results are stored in `output/briefings.db` (SQLite — no server required):

| Table | Contents |
| --- | --- |
| `runs` | One row per run: topic, timestamp, raw headlines, aggregation state |
| `outputs` | One row per AI output per run: type, name, content |
| `outbox` | One row per output×destination: delivery status and formatted message |

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
  "outputs": [
    {"type": "narrative", "name": "Daily Digest",  "max_words": 500, "dest": "telegram"},
    {"type": "tweet",     "name": "Tweet Summary", "max_chars": 280, "dest": "x"}
  ],
  "searches": [
    {"emoji": "📰", "title": "LATEST MY TOPIC NEWS", "query": "my topic news today", "count": 5, "category": "news"},
    {"emoji": "📊", "title": "SECTION NAME",          "query": "your search query",  "count": 4, "category": "news"}
  ]
}
```

> **Tip:** Name one search section with "latest" in the title (e.g. `LATEST MY TOPIC NEWS`) and the tweet output will draw exclusively from that section.

Then run:

```bash
python briefing.py my_briefing --mock --dry-run
python publish.py --dry-run
```

## Scheduling on macOS (launchd)

`run.sh` wraps briefing + publish in a single script so launchd only needs one job. publish.py only fires if briefing.py exits successfully (`set -e` in the script handles this).

### 1. Create the plist

Save as `~/Library/LaunchAgents/com.briefing.robotics.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefing.robotics</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/projects/briefing/run.sh</string>
        <string>robotics</string>
        <string>x</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/briefing.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/briefing.error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Replace `YOUR_USER` and adjust the `Hour`/`Minute` to your preferred schedule.

### 2. Load and test

```bash
# Load the job
launchctl load ~/Library/LaunchAgents/com.briefing.robotics.plist

# Run it immediately to test
launchctl start com.briefing.robotics

# Check logs
tail -f output/briefing.log
tail -f output/briefing.error.log

# Unload if you need to edit the plist
launchctl unload ~/Library/LaunchAgents/com.briefing.robotics.plist
```

### Example: morning briefing + hourly tweet (UK capital markets)

Two plists — one fires at 7am for the full briefing (narrative→Telegram, tweet→X), another fires every hour for a quick tweet→X update.

**`com.briefing.uk_capital_markets.plist`** — 7am daily:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefing.uk_capital_markets</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/projects/briefing/run.sh</string>
        <string>uk_capital_markets</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/uk_capital_markets.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/uk_capital_markets.error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

**`com.briefing.uk_capital_markets_update.plist`** — hourly tweet:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.briefing.uk_capital_markets_update</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USER/projects/briefing/run.sh</string>
        <string>uk_capital_markets_update</string>
    </array>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>15</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Hour</key><integer>16</integer><key>Minute</key><integer>0</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/uk_capital_markets_update.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USER/projects/briefing/output/uk_capital_markets_update.error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

> launchd doesn't support a simple "every hour" interval with `StartCalendarInterval` — you list each hour explicitly. The above covers 8am–4pm (market hours). Adjust as needed.

### Notes

- launchd runs jobs as your user, so credentials in `.env` are picked up normally
- If the machine is asleep at the scheduled time, the job is skipped — it does not catch up on wake
- publish.py is safe to run independently at any time; it skips already-published outbox entries

## Output structure

```text
output/
  briefings.db                          # SQLite — all runs, outputs, and outbox
  2026-03-14_12-00-00_robotics/
    raw_briefing.txt                    # formatted headlines (HTML)
    narrative.txt                       # AI narrative output
    tweet.txt                           # AI tweet output
```
