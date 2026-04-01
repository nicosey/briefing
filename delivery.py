import json
import os
import sys
import urllib.request

from config import log


# ── base ─────────────────────────────────────────────────────

class Delivery:
    """Base class for briefing delivery destinations."""

    def send(self, message):
        raise NotImplementedError

    def send_long(self, message):
        """Send a message that may exceed the destination's size limit.
        Default: single send. Override if chunking is needed."""
        self.send(message)


# ── telegram ─────────────────────────────────────────────────

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
        chunks  = message.split("\n\n")
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


# ── console ──────────────────────────────────────────────────

class ConsoleDelivery(Delivery):
    """Prints to stdout — used for --dry-run."""

    def send(self, message):
        print(message)


# ── multi ────────────────────────────────────────────────────

class MultiDelivery(Delivery):
    """Fans out to multiple delivery destinations."""

    def __init__(self, deliveries):
        self.deliveries = deliveries

    def send(self, message):
        for d in self.deliveries:
            d.send(message)

    def send_long(self, message):
        for d in self.deliveries:
            d.send_long(message)


# ── registry ─────────────────────────────────────────────────

def _make_telegram(name):
    """Resolve token and chat_id for a telegram dest name.
    'telegram'          -> TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
    'telegram_robotics' -> TELEGRAM_BOT_TOKEN_ROBOTICS / TELEGRAM_CHAT_ID_ROBOTICS
    """
    suffix = name[len("telegram_"):].upper() if name != "telegram" else ""
    token_key   = f"TELEGRAM_BOT_TOKEN_{suffix}" if suffix else "TELEGRAM_BOT_TOKEN"
    chat_key    = f"TELEGRAM_CHAT_ID_{suffix}"   if suffix else "TELEGRAM_CHAT_ID"
    token   = os.environ.get(token_key, "")
    chat_id = os.environ.get(chat_key, "")
    if not token or not chat_id:
        log(f"❌ Missing env vars for '{name}': need {token_key} and {chat_key}")
        sys.exit(1)
    return TelegramDelivery(token=token, chat_id=chat_id)


def make_delivery(dest, dry_run, cfg=None):
    """Build a Delivery for a dest string (comma-separated names).
    Supports 'console', 'telegram', and 'telegram_<name>' for named bots.
    """
    if dry_run:
        return ConsoleDelivery()

    names = [d.strip() for d in dest.split(",") if d.strip()]
    deliveries = []
    for name in names:
        if name == "console":
            deliveries.append(ConsoleDelivery())
        elif name == "telegram" or name.startswith("telegram_"):
            deliveries.append(_make_telegram(name))
        else:
            log(f"❌ Unknown delivery destination: '{name}'. Use 'telegram', 'telegram_<name>', or 'console'.")
            sys.exit(1)

    return deliveries[0] if len(deliveries) == 1 else MultiDelivery(deliveries)


