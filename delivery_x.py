import json
import os

from config import TWITTER_USERNAME, TWITTER_PASSWORD, TWITTER_HEADLESS, TWITTER_SESSION, log
from delivery import Delivery


class XDelivery(Delivery):
    """Posts tweet-sized messages to X (Twitter) via Playwright browser automation.

    Messages longer than MAX_CHARS are silently skipped — so only the
    'tweet' output type (≤280 chars) will actually be posted; the raw
    briefing and narrative pass through without error.

    Requires: pip install playwright && playwright install chromium

    Credentials: set TWITTER_USERNAME and TWITTER_PASSWORD in .env
    Session:     cookies saved to TWITTER_SESSION after first login
    Headless:    set TWITTER_HEADLESS=false to watch the browser (useful for debugging)
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
                page.goto("https://x.com/compose/tweet", timeout=20000)
                page.wait_for_load_state("networkidle", timeout=15000)

                # Login if redirected away from compose
                if "login" in page.url or page.url.rstrip("/") in ("https://x.com", "https://twitter.com"):
                    if not self._login(page):
                        browser.close()
                        return False
                    page.goto("https://x.com/compose/tweet", timeout=20000)
                    page.wait_for_load_state("networkidle", timeout=15000)

                # Type into the compose box
                editor = page.locator('[data-testid="tweetTextarea_0"]')
                editor.wait_for(timeout=10000)
                editor.click()
                page.keyboard.type(message, delay=30)

                # Post
                post_btn = page.locator('[data-testid="tweetButtonInline"]')
                post_btn.wait_for(timeout=5000)
                post_btn.click()
                page.wait_for_timeout(2000)

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
            page.goto("https://x.com/login", timeout=20000)
            page.wait_for_load_state("networkidle", timeout=15000)

            page.locator('input[autocomplete="username"]').fill(self.username)
            page.keyboard.press("Enter")
            page.wait_for_timeout(1500)

            page.locator('input[name="password"]').wait_for(timeout=8000)
            page.locator('input[name="password"]').fill(self.password)
            page.keyboard.press("Enter")
            page.wait_for_load_state("networkidle", timeout=15000)

            if "login" in page.url:
                log("  ❌ X: login failed — check TWITTER_USERNAME / TWITTER_PASSWORD in .env")
                return False

            log("  ✅ X: logged in")
            return True
        except Exception as e:
            log(f"  ❌ X: login error: {e}")
            return False
