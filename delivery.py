import json
import os
import sys
import urllib.request

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_HEADLESS, TWITTER_SESSION,
    log,
)


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


# ── x (twitter) ──────────────────────────────────────────────

class XDelivery(Delivery):
    """Posts tweet-sized messages to X via Playwright browser automation.

    Messages longer than MAX_CHARS are silently skipped — so only the
    'tweet' output type (≤280 chars) will actually be posted.

    Requires: pip install playwright && playwright install chromium
    Credentials: TWITTER_USERNAME / TWITTER_PASSWORD in .env
    Session: cookies saved after first login and reused on subsequent runs
    Headless: set TWITTER_HEADLESS=false to watch the browser (useful for debugging)
    """
    MAX_CHARS = 280

    def __init__(self, username, password, headless=True, session_file=TWITTER_SESSION):
        self.username     = username
        self.password     = password
        self.headless     = headless
        self.session_file = session_file

    def send(self, message):
        if len(message) > self.MAX_CHARS:
            log(f"  ℹ X: skipping ({len(message)} chars > {self.MAX_CHARS})")
            return False

        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        except ImportError:
            log("  ❌ X: playwright not installed.")
            log("     Run: pip install playwright && playwright install chromium")
            return False

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()

            # Restore saved session if available
            if os.path.isfile(self.session_file):
                try:
                    with open(self.session_file) as f:
                        context.add_cookies(json.load(f))
                    log("  ℹ X: loaded saved session")
                except Exception:
                    pass

            page = context.new_page()

            try:
                log("  ℹ X: navigating to compose...")
                page.goto("https://x.com/compose/tweet", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=20000)
                log(f"  ℹ X: landed on {page.url}")

                # Login if redirected away from compose
                if "login" in page.url or page.url.rstrip("/") in ("https://x.com", "https://twitter.com"):
                    if not self._login(page):
                        browser.close()
                        return False
                    log("  ℹ X: navigating to compose after login...")
                    page.goto("https://x.com/compose/tweet", timeout=30000)
                    page.wait_for_load_state("networkidle", timeout=20000)
                    log(f"  ℹ X: landed on {page.url}")

                # Type into the compose box
                log("  ℹ X: waiting for compose box...")
                editor = page.locator('[data-testid="tweetTextarea_0"]')
                editor.wait_for(timeout=15000)
                editor.click()
                page.keyboard.type(message, delay=30)

                # Post
                log("  ℹ X: clicking post...")
                post_btn = page.locator('[data-testid="tweetButtonInline"]')
                post_btn.wait_for(timeout=10000)
                post_btn.click()
                page.wait_for_timeout(3000)

                # Persist session cookies
                os.makedirs(os.path.dirname(self.session_file) or ".", exist_ok=True)
                with open(self.session_file, "w") as f:
                    json.dump(context.cookies(), f)

                log("  ✅ X: posted")
                browser.close()
                return True

            except PWTimeout:
                log("  ❌ X: timed out waiting for page element")
                browser.close()
                return False
            except Exception as e:
                log(f"  ❌ X: {e}")
                browser.close()
                return False

    def _login(self, page):
        log("  ℹ X: logging in...")
        try:
            page.goto("https://x.com/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=20000)

            log("  ℹ X: entering username...")
            page.locator('input[autocomplete="username"]').fill(self.username)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            log(f"  ℹ X: after username, url={page.url}")

            # X sometimes asks for email/phone verification before password
            if page.locator('input[data-testid="ocfEnterTextTextInput"]').is_visible():
                log("  ℹ X: identity verification step — entering username again...")
                page.locator('input[data-testid="ocfEnterTextTextInput"]').fill(self.username)
                page.keyboard.press("Enter")
                page.wait_for_timeout(2000)

            log("  ℹ X: entering password...")
            page.locator('input[name="password"]').wait_for(timeout=10000)
            page.locator('input[name="password"]').fill(self.password)
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=20000)
            log(f"  ℹ X: after password, url={page.url}")

            if "login" in page.url:
                log("  ❌ X: login failed — check X_USERNAME / X_PASSWORD in .env")
                return False

            log("  ✅ X: logged in")
            return True
        except Exception as e:
            log(f"  ❌ X: login error: {e}")
            return False


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
# To add a new destination: implement a Delivery subclass and add it here.

REGISTRY = {
    "telegram": lambda cfg: TelegramDelivery(
        token   = TELEGRAM_BOT_TOKEN,
        chat_id = cfg.get("telegram_chat_id", TELEGRAM_CHAT_ID),
    ),
    "x": lambda cfg: XDelivery(
        username = TWITTER_USERNAME,
        password = TWITTER_PASSWORD,
        headless = TWITTER_HEADLESS,
    ),
    "console": lambda cfg: ConsoleDelivery(),
}


def make_delivery(dest, dry_run, cfg=None):
    """Build a Delivery for a specific dest string (comma-separated names)."""
    if dry_run:
        return ConsoleDelivery()

    cfg   = cfg or {}
    names = [d.strip() for d in dest.split(",") if d.strip()]

    deliveries = []
    for name in names:
        if name not in REGISTRY:
            log(f"❌ Unknown delivery destination: {name}. Choose from: {', '.join(REGISTRY)}")
            sys.exit(1)
        deliveries.append(REGISTRY[name](cfg))

    return deliveries[0] if len(deliveries) == 1 else MultiDelivery(deliveries)


def get_delivery(dry_run, cfg=None):
    dest = os.environ.get("BRIEFING_DEST", "console")
    return make_delivery(dest, dry_run, cfg)
