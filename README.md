# briefing

A lightweight daily news briefing pipeline. Searches for recent news via [SearXNG](https://github.com/searxng/searxng), generates an AI narrative via [Ollama](https://ollama.com), and delivers it to Telegram.

## How it works

1. **Search** — runs a set of queries against a local SearXNG instance
2. **Summarise** — feeds the results to a local Ollama model to write a narrative
3. **Deliver** — sends both the raw headlines and the AI story to a Telegram chat
4. **Save** *(optional)* — stores results in a timestamped folder under `output/`
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
| `--save` | Write results to `output/<timestamp>_<topic>/` |
| `--lookback N` | Include last N minutes of saved summaries as AI context |

**Available topics:** `robotics`, `uk_capital_markets`, `data_centres`

### Examples

```bash
# Test locally with no services
python briefing.py robotics --mock --dry-run

# Real run, save output
python briefing.py robotics --save

# Real run with trend aggregation from the last 2 hours
python briefing.py robotics --save --lookback 120
```

## Aggregation

When `--save` and `--lookback` are both set, each run:
- Looks back through `output/` for recent summaries of the same topic
- Injects them into the AI prompt so it can note continuity and divergence
- Marks those prior runs as aggregated so they aren't re-used unnecessarily
- Records which runs were aggregated in `meta.json`

The lookback window can also be set per-topic in the config JSON:
```json
"lookback_minutes": 120
```

## Adding a topic

Create a JSON file in `config/`:

```json
{
  "title": "My Briefing",
  "header_emoji": "📋",
  "footer_emoji": "🔍",
  "ai_persona": "a analyst writing a daily briefing",
  "ai_topic": "Today's Update",
  "lookback_minutes": 120,
  "searches": [
    {
      "emoji": "📰",
      "title": "SECTION NAME",
      "query": "your search query",
      "count": 5,
      "category": "news"
    }
  ]
}
```

Then run:
```bash
python briefing.py my_briefing --mock --dry-run
```

## Output structure

```
output/
  2026-03-14_12-00-00_robotics/
    raw_briefing.txt   # formatted headlines (HTML)
    narrative.txt      # AI-generated story (HTML)
    meta.json          # topic, timestamp, aggregation state
```
