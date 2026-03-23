import os
import sys
import json
from datetime import datetime


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
TWITTER_USERNAME   = os.environ.get("TWITTER_USERNAME", "")
TWITTER_PASSWORD   = os.environ.get("TWITTER_PASSWORD", "")
TWITTER_HEADLESS   = os.environ.get("TWITTER_HEADLESS", "true").lower() != "false"
TWITTER_SESSION    = os.environ.get("TWITTER_SESSION", os.path.join("output", ".twitter_session.json"))


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


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
