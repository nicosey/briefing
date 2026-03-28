"""
Interactive X login — run this once to save a session.
Opens a real browser window so you can log in manually (handles
CAPTCHAs, 2FA, and any other challenges automatically).
Once you're logged in, press Enter in the terminal to save the session.
"""
import os
from config import TWITTER_SESSION, log

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Run: pip install playwright && playwright install chromium")
    raise SystemExit(1)

with sync_playwright() as p:
    browser = p.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/123.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    page    = context.new_page()

    page.goto("https://x.com/login")
    print()
    print("Log in to X in the browser window.")
    print("Once you are fully logged in, come back here and press Enter.")
    print()
    input("Press Enter when logged in → ")

    os.makedirs(os.path.dirname(TWITTER_SESSION) or ".", exist_ok=True)
    context.storage_state(path=TWITTER_SESSION)

    log(f"✅ Session saved to {TWITTER_SESSION}")
    browser.close()
