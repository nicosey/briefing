# briefing

A lightweight daily news briefing pipeline. Searches for recent news via [SearXNG](https://github.com/searxng/searxng), generates AI outputs via [Ollama](https://ollama.com), and delivers them to Telegram.

## How it works

1. **Search** — runs a set of queries against a local SearXNG instance
2. **Generate** — feeds the results to a local Ollama model to produce each configured output (e.g. narrative, tweet)
3. **Deliver** — sends the raw headlines and all AI outputs to a Telegram chat
4. **Save** *(optional)* — stores results in SQLite + a timestamped folder under `output/`
5. **Aggregate** *(optional)* — injects recent saved summaries as context so the AI can track trends across runs

## Requirements

- Python 3.8+ (no external dependencies)
- [SearXNG](https://github.com/searxng/searxng) running locally
- [Ollama](https://ollama.com) running locally with a model pulled
- A Telegram bot token and chat ID

## Setup

```bash
cp .env.example .env
# edit .env with your values
```

**.env**
```
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
SEARXNG_URL=http://localhost:8888
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=qwen3-coder:30b
```

## Usage

```bash
python briefing.py <topic> [options]
```

| Option | Description |
|---|---|
| `--mock` | Fake SearXNG + Ollama — no services needed |
| `--dry-run` | Skip Telegram, print to terminal instead |
| `--save` | Write results to SQLite DB + `output/<timestamp>_<topic>/` |
| `--lookback N` | Include last N minutes of saved summaries as AI context |

**Available topics:** `robotics`, `uk_capital_markets`, `data_centres`, `bjj`

### Examples

```bash
# Test locally with no services
python briefing.py robotics --mock --dry-run

# Real run, save output
python briefing.py robotics --save

# Real run with trend aggregation from the last 2 hours
python briefing.py robotics --save --lookback 120
```

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

When `--save` and `--lookback` are both set, each run:
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
    {"type": "narrative", "name": "Daily Digest",  "max_words": 500},
    {"type": "tweet",     "name": "Tweet Summary", "max_chars": 280}
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
```

## Output structure

```
output/
  briefings.db                          # SQLite — all runs and outputs
  2026-03-14_12-00-00_robotics/
    raw_briefing.txt                    # formatted headlines (HTML)
    narrative.txt                       # AI narrative output
    tweet.txt                           # AI tweet output
```
