"""Quick test: write a dummy .md file to the Astro repo and push to GitHub."""
import sys
from datetime import datetime
from delivery import _make_github

delivery = _make_github()
now = datetime.now()

test_md = f"""\
---
title: "GitHub Connection Test"
description: "Automated connection test from test_github.py"
pubDate: {now.strftime('%Y-%m-%dT%H:%M:%S')}
topic: test
model: test
---

This is a test file created by test_github.py at {now.strftime('%Y-%m-%d %H:%M:%S')}. Safe to delete.
"""

print("Testing GitHub delivery...")
ok = delivery.send(test_md)
sys.exit(0 if ok else 1)
