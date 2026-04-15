"""Quick test: write a dummy .md file to the Astro repo and push to GitHub."""
import sys
from delivery import _make_github

delivery = _make_github()

test_md = """\
---
title: "GitHub Connection Test"
date: 2026-01-01
time: "00:00"
topic: test
model: test
---

This is a test file created by test_github.py. Safe to delete.
"""

print("Testing GitHub delivery...")
ok = delivery.send(test_md)
sys.exit(0 if ok else 1)
