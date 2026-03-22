import json
import urllib.request

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, log


class Delivery:
    """Base class for briefing delivery destinations."""

    def send(self, message):
        raise NotImplementedError

    def send_long(self, message):
        """Send a message that may exceed the destination's size limit.
        Default: single send. Override if chunking is needed."""
        self.send(message)


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
        chunks = message.split("\n\n")
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


class ConsoleDelivery(Delivery):
    """Prints to stdout — used for --dry-run."""

    def send(self, message):
        print(message)


# Registry: name -> factory.
# To add a new destination, implement a Delivery subclass and add it here.
REGISTRY = {
    "telegram": lambda: TelegramDelivery(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID),
    "console":  lambda: ConsoleDelivery(),
}


def get_delivery(dry_run):
    import os, sys
    if dry_run:
        return ConsoleDelivery()
    dest = os.environ.get("BRIEFING_DEST", "telegram")
    if dest not in REGISTRY:
        log(f"❌ Unknown delivery destination: {dest}. Choose from: {', '.join(REGISTRY)}")
        sys.exit(1)
    return REGISTRY[dest]()
