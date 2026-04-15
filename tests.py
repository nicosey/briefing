"""
Test suite for the briefing pipeline.
Run: python3 tests.py

No external services required — all tests use mocks or temp dirs.
"""
import os
import sys
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock


# ── format tests ──────────────────────────────────────────────

class TestParseFormatmatter(unittest.TestCase):

    def setUp(self):
        from format import parse_frontmatter
        self.parse = parse_frontmatter

    def test_parses_basic_fields(self):
        md = '---\ntitle: "My Title"\ndate: 2026-04-08\ntopic: robotics\n---\n\nBody.'
        meta = self.parse(md)
        self.assertEqual(meta["title"], "My Title")
        self.assertEqual(meta["date"], "2026-04-08")
        self.assertEqual(meta["topic"], "robotics")

    def test_returns_empty_for_no_frontmatter(self):
        self.assertEqual(self.parse("No frontmatter here."), {})

    def test_strips_quotes_from_values(self):
        meta = self.parse('---\ntitle: "Quoted"\n---\n')
        self.assertEqual(meta["title"], "Quoted")


class TestBuildMarkdownMessage(unittest.TestCase):

    def setUp(self):
        from format import build_markdown_message
        self.build = build_markdown_message

    def _cfg(self, **kwargs):
        base = {"title": "Test Briefing", "ai_topic": "Test Topic",
                "briefing_title": "Morning Start", "_topic": "uk_capital_markets"}
        base.update(kwargs)
        return base

    def test_contains_frontmatter_block(self):
        msg = self.build("Content here.", {}, self._cfg())
        self.assertTrue(msg.startswith("---\n"))
        self.assertIn("\n---\n", msg)

    def test_contains_title_topic_and_pubdate(self):
        msg = self.build("Content.", {}, self._cfg())
        self.assertIn("Morning Start", msg)
        self.assertIn("uk_capital_markets", msg)
        self.assertIn("pubDate:", msg)
        self.assertIn("description:", msg)

    def test_contains_content(self):
        msg = self.build("The actual content.", {}, self._cfg())
        self.assertIn("The actual content.", msg)

    def test_falls_back_to_ai_topic(self):
        cfg = self._cfg()
        del cfg["briefing_title"]
        msg = self.build("Content.", {}, cfg)
        self.assertIn("Test Topic", msg)


class TestSplitToLimit(unittest.TestCase):

    def setUp(self):
        from format import _split_to_limit
        self.split = _split_to_limit

    def test_short_text_returned_as_is(self):
        self.assertEqual(self.split("Short text.", 280), ["Short text."])

    def test_splits_at_paragraph_boundary(self):
        text = ("A" * 150) + "\n\n" + ("B" * 150)
        chunks = self.split(text, 200)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 200 for c in chunks))

    def test_splits_at_sentence_boundary(self):
        text = ("Word " * 30) + ". " + ("Word " * 30)
        chunks = self.split(text, 100)
        self.assertTrue(all(len(c) <= 100 for c in chunks))

    def test_all_chunks_within_limit(self):
        text = "This is a fairly long sentence that should be split. " * 10
        chunks = self.split(text, 80)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), 80)


class TestMarkdownDests(unittest.TestCase):

    def test_markdown_and_github_in_set(self):
        from format import MARKDOWN_DESTS
        self.assertIn("markdown", MARKDOWN_DESTS)
        self.assertIn("github", MARKDOWN_DESTS)


class TestValidateAstroFrontmatter(unittest.TestCase):

    def setUp(self):
        from format import validate_astro_frontmatter
        self.validate = validate_astro_frontmatter

    def _valid(self):
        return (
            '---\ntitle: "My Title"\ndescription: "A description"\n'
            'pubDate: 2026-04-08T18:00:00\ntopic: test\n---\n\nBody.'
        )

    def test_valid_frontmatter_returns_no_errors(self):
        self.assertEqual(self.validate(self._valid()), [])

    def test_missing_title_returns_error(self):
        md = '---\ndescription: "desc"\npubDate: 2026-04-08T18:00:00\n---\n'
        errors = self.validate(md)
        self.assertTrue(any("title" in e for e in errors))

    def test_missing_description_returns_error(self):
        md = '---\ntitle: "T"\npubDate: 2026-04-08T18:00:00\n---\n'
        errors = self.validate(md)
        self.assertTrue(any("description" in e for e in errors))

    def test_missing_pubdate_returns_error(self):
        md = '---\ntitle: "T"\ndescription: "D"\n---\n'
        errors = self.validate(md)
        self.assertTrue(any("pubDate" in e for e in errors))

    def test_invalid_pubdate_returns_error(self):
        md = '---\ntitle: "T"\ndescription: "D"\npubDate: not-a-date\n---\n'
        errors = self.validate(md)
        self.assertTrue(any("Invalid pubDate" in e for e in errors))

    def test_no_frontmatter_returns_error(self):
        errors = self.validate("No frontmatter here.")
        self.assertTrue(len(errors) > 0)


# ── delivery tests ────────────────────────────────────────────

class TestMarkdownDelivery(unittest.TestCase):

    def setUp(self):
        from delivery import MarkdownDelivery
        self.cls = MarkdownDelivery

    def _msg(self, topic="robotics"):
        return (
            f'---\ntitle: "Test"\ndescription: "A test."\n'
            f'pubDate: 2026-04-08T09:00:00\ntopic: {topic}\nmodel: test\n---\n\nContent.\n'
        )

    def test_writes_md_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self.cls(tmpdir)
            ok = d.send(self._msg())
            self.assertTrue(ok)
            files = os.listdir(tmpdir)
            self.assertEqual(len(files), 1)
            self.assertTrue(files[0].endswith(".md"))

    def test_filename_includes_date_and_topic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self.cls(tmpdir)
            d.send(self._msg("robotics"))
            filename = os.listdir(tmpdir)[0]
            self.assertIn("2026-04-08", filename)
            self.assertIn("robotics", filename)

    def test_file_content_matches_message(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self.cls(tmpdir)
            msg = self._msg("test")
            d.send(msg)
            filename = os.listdir(tmpdir)[0]
            with open(os.path.join(tmpdir, filename)) as f:
                self.assertEqual(f.read(), msg)


class TestGitHubDelivery(unittest.TestCase):

    def setUp(self):
        from delivery import GitHubDelivery
        self.cls = GitHubDelivery

    def _msg(self):
        return (
            '---\ntitle: "GitHub Test"\ndescription: "A test."\n'
            'pubDate: 2026-04-08T09:00:00\ntopic: test\nmodel: test\n---\n\nTest content.\n'
        )

    def test_pushes_on_successful_write(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = "content"
            os.makedirs(os.path.join(tmpdir, md_dir))
            d = self.cls(repo_path=tmpdir, md_dir=md_dir, branch="main")
            with patch.object(d, "_git") as mock_git:
                with patch.object(d.__class__.__bases__[0], "send", return_value=True):
                    d.send(self._msg())
                    calls = [c.args[0] for c in mock_git.call_args_list]
                    self.assertIn("add", calls)
                    self.assertIn("commit", calls)
                    self.assertIn("push", calls)

    def test_skips_git_if_file_write_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            d = self.cls(repo_path=tmpdir, md_dir="content", branch="main")
            with patch.object(d.__class__.__bases__[0], "send", return_value=False):
                with patch.object(d, "_git") as mock_git:
                    result = d.send(self._msg())
                    self.assertFalse(result)
                    mock_git.assert_not_called()

    def test_returns_false_on_git_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            md_dir = "content"
            os.makedirs(os.path.join(tmpdir, md_dir))
            d = self.cls(repo_path=tmpdir, md_dir=md_dir, branch="main")
            with patch.object(d.__class__.__bases__[0], "send", return_value=True):
                with patch.object(d, "_git", side_effect=RuntimeError("auth failed")):
                    result = d.send(self._msg())
                    self.assertFalse(result)


class TestMakeDelivery(unittest.TestCase):

    def test_dry_run_returns_console(self):
        from delivery import make_delivery, ConsoleDelivery
        d = make_delivery("telegram", dry_run=True)
        self.assertIsInstance(d, ConsoleDelivery)

    def test_console_dest(self):
        from delivery import make_delivery, ConsoleDelivery
        d = make_delivery("console", dry_run=False)
        self.assertIsInstance(d, ConsoleDelivery)

    def test_markdown_dest(self):
        from delivery import make_delivery, MarkdownDelivery
        with patch.dict(os.environ, {"MARKDOWN_OUTPUT_DIR": "/tmp/md"}):
            d = make_delivery("markdown", dry_run=False)
            self.assertIsInstance(d, MarkdownDelivery)

    def test_unknown_dest_exits(self):
        from delivery import make_delivery
        with self.assertRaises(SystemExit):
            make_delivery("unknown_dest", dry_run=False)

    def test_multi_dest(self):
        from delivery import make_delivery, MultiDelivery
        with patch.dict(os.environ, {"MARKDOWN_OUTPUT_DIR": "/tmp/md"}):
            d = make_delivery("console,markdown", dry_run=False)
            self.assertIsInstance(d, MultiDelivery)


# ── search / mock tests ───────────────────────────────────────

class TestMockFetchResults(unittest.TestCase):

    def test_returns_one_section_per_search(self):
        from search import mock_fetch_results
        searches = [
            {"title": "NEWS", "emoji": "📰", "count": 3},
            {"title": "TECH", "emoji": "💻", "count": 2},
        ]
        results = mock_fetch_results(searches)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["section"], "NEWS")
        self.assertEqual(len(results[0]["results"]), 3)

    def test_each_result_has_required_keys(self):
        from search import mock_fetch_results
        results = mock_fetch_results([{"title": "X", "emoji": "🔹", "count": 2}])
        for r in results[0]["results"]:
            self.assertIn("title", r)
            self.assertIn("url", r)
            self.assertIn("snippet", r)


# ── ai mock tests ─────────────────────────────────────────────

class TestMockOutput(unittest.TestCase):

    def _cfg(self):
        return {"ai_topic": "Test Topic", "title": "Test", "_topic": "test",
                "briefing_title": ""}

    def test_narrative_mock_returns_string(self):
        from ai import mock_output
        result = mock_output({"type": "narrative"}, self._cfg())
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_tweet_mock_returns_string(self):
        from ai import mock_output
        result = mock_output({"type": "tweet"}, self._cfg())
        self.assertIsInstance(result, str)

    def test_thread_mock_uses_paragraph_splitting(self):
        from ai import mock_output
        result = mock_output({"type": "thread", "max_chars_per_post": 280,
                               "numbered": True}, self._cfg())
        self.assertIsInstance(result, str)
        posts = result.split("\n---\n")
        self.assertGreater(len(posts), 1)
        for post in posts:
            self.assertLessEqual(len(post), 280)

    def test_thread_mock_uses_source_content(self):
        from ai import mock_output
        source = "Para one content.\n\nPara two content.\n\nPara three content."
        result = mock_output({"type": "thread", "max_chars_per_post": 280,
                               "numbered": True}, self._cfg(),
                             source_content=source)
        self.assertIn("Para one", result)
        self.assertIn("Para two", result)


# ── github connection test ────────────────────────────────────

class TestGitHubConnection(unittest.TestCase):
    """Integration test — only runs if GITHUB_REPO_PATH is set in env."""

    def setUp(self):
        self.repo_path = os.environ.get("GITHUB_REPO_PATH", "")
        if not self.repo_path or not os.path.isdir(self.repo_path):
            self.skipTest("GITHUB_REPO_PATH not set or path does not exist — skipping live GitHub test")

    def test_repo_path_is_git_repo(self):
        self.assertTrue(
            os.path.isdir(os.path.join(self.repo_path, ".git")),
            f"{self.repo_path} is not a git repository"
        )

    def test_can_run_git_status(self):
        import subprocess
        result = subprocess.run(
            ["git", "-C", self.repo_path, "status"],
            capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
