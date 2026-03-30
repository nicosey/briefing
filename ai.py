import json
import urllib.request

from config import OLLAMA_URL, OLLAMA_MODEL, log


# ── prompt builders ──────────────────────────────────────────

def _results_text(results_data):
    out = ""
    for section in results_data:
        out += f"\n{section['section']}:\n"
        for r in section["results"]:
            out += f"- {r['title']}"
            if r["snippet"]:
                out += f": {r['snippet']}"
            out += "\n"
    return out


def _narrative_prompt(output_cfg, results_data, cfg, previous_narratives):
    history_block = ""
    if previous_narratives:
        history_block = "\nPREVIOUS SUMMARIES (for context and trend continuity):\n"
        for ts, text in previous_narratives:
            history_block += f"\n[{ts[:16].replace('T', ' ')}]\n{text}\n"
        history_block += "\n---\n"

    agg_instruction = (
        "- Where relevant, note how today's news continues or diverges from the previous summaries above\n"
        if previous_narratives else ""
    )

    max_words = output_cfg.get("max_words", 500)

    briefing_instruction = cfg.get("briefing_instruction", "")
    if briefing_instruction:
        briefing_instruction = f"- {briefing_instruction}\n"

    return f"""/no_think
You are {cfg['ai_persona']}.
Based on today's news below, write a concise, engaging narrative summary called "{cfg['ai_topic']}".

Rules:
- Write 3-4 short paragraphs maximum
- Lead with the most important story
- Mention key companies and deals
- Add brief analysis on what trends you see
- Keep it under {max_words} words
- Write in a professional but accessible tone
- Do NOT use markdown formatting, just plain text
- End with one sentence on what to watch next
{briefing_instruction}{agg_instruction}
{history_block}TODAY'S RAW NEWS DATA:
{_results_text(results_data)}

Write the narrative now:"""


def _thread_prompt(output_cfg, results_data, cfg, previous_tweets=None, source_content=None):
    num_posts  = output_cfg.get("num_posts", 4)
    max_chars  = output_cfg.get("max_chars_per_post", 280)
    numbered   = output_cfg.get("numbered", True)
    numbering  = f"- Start each post with its position, e.g. '1/{num_posts}', '2/{num_posts}'\n" if numbered else ""

    briefing_instruction = cfg.get("briefing_instruction", "")
    if briefing_instruction:
        briefing_instruction = f"- {briefing_instruction}\n"

    if source_content:
        input_block = f"BRIEFING TO THREAD:\n{source_content}"
        task = "Break the briefing below into an X (Twitter) thread"
    else:
        latest_sections = [s for s in results_data if "latest" in s["section"].lower()]
        feed = latest_sections if latest_sections else results_data
        input_block = f"LATEST NEWS:\n{_results_text(feed)}"
        task = "Write an X (Twitter) thread covering the most important current stories"

    return f"""/no_think
You are {cfg['ai_persona']}.
{task} of exactly {num_posts} posts.

Rules:
- Write exactly {num_posts} posts separated by a line containing only: ---
- Each post must be under {max_chars} characters including the number prefix
{numbering}- Each post must be self-contained and make sense on its own
- Cover the key points in order — do not skip or invent content
- End the final post with 2-3 relevant hashtags
- Write in present tense, professional but accessible tone
- Do NOT use markdown formatting
{briefing_instruction}
{input_block}

Write the thread now:"""


def _tweet_prompt(output_cfg, results_data, cfg, previous_tweets=None):
    max_chars = output_cfg.get("max_chars", 280)

    # Prefer a section explicitly marked as latest news, otherwise use all
    latest_sections = [s for s in results_data if "latest" in s["section"].lower()]
    feed = latest_sections if latest_sections else results_data

    recent_block = ""
    if previous_tweets:
        recent_block = "\nRECENT TWEETS ALREADY POSTED (do NOT repeat these stories):\n"
        for t in previous_tweets:
            recent_block += f"- {t}\n"
        recent_block += "\n"

    return f"""/no_think
You are {cfg['ai_persona']}.
Based on the latest news below, write a single tweet-sized update about the most breaking or recent story.

Rules:
- Maximum {max_chars} characters including spaces
- Focus on the single most recent or newsworthy headline
- One or two sentences maximum
- Write in present tense
- End with 1-2 relevant hashtags
- Pick a DIFFERENT story from any recently posted tweets listed below
{recent_block}
LATEST NEWS:
{_results_text(feed)}

Write the tweet now:"""


# ── prompt registry ──────────────────────────────────────────
# To add a new output type: add an entry here returning a prompt string.

_PROMPT_BUILDERS = {
    "narrative": _narrative_prompt,
    "tweet":     _tweet_prompt,
    "thread":    _thread_prompt,
}


# ── public API ───────────────────────────────────────────────

def _ollama_call(prompt, max_tokens=500):
    """Single Ollama call, returns stripped text or None."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": max_tokens}
    }).encode("utf-8")
    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data.get("message", {}).get("content", "").strip() or None
    except Exception as e:
        log(f"  ⚠ Ollama call failed: {e}")
        return None


def _generate_thread_from_paragraphs(output_cfg, source_content, cfg):
    """Split narrative into paragraphs, tighten any that exceed the char limit."""
    max_chars = output_cfg.get("max_chars_per_post", 280)
    numbered  = output_cfg.get("numbered", True)

    paragraphs = [p.strip() for p in source_content.split("\n\n") if p.strip()]
    if not paragraphs:
        return None

    n          = len(paragraphs)
    prefix_len = len(f"{n}/{n} ") if numbered else 0
    effective  = max_chars - prefix_len

    posts = []
    for i, para in enumerate(paragraphs):
        if len(para) <= effective:
            posts.append(para)
        else:
            log(f"  ℹ thread: tightening paragraph {i+1} ({len(para)} → ≤{effective} chars)...")
            tightened = _ollama_call(
                f"/no_think\nRewrite this to fit within {effective} characters for X (Twitter). "
                f"Keep all key information. Present tense, professional tone. Output only the rewritten text.\n\n"
                f"TEXT:\n{para}\n\nRewritten:",
                max_tokens=200
            )
            posts.append(tightened if tightened else para[:effective])

    if numbered:
        posts = [f"{i+1}/{n} {post}" for i, post in enumerate(posts)]

    log(f"  ✅ thread: {n} posts from narrative paragraphs")
    return "\n---\n".join(posts)


def generate_output(output_cfg, results_data, cfg, previous_narratives=None, source_content=None):
    output_type = output_cfg.get("type", "narrative")

    # Thread without fixed num_posts: split narrative paragraphs
    if output_type == "thread" and "num_posts" not in output_cfg and source_content:
        return _generate_thread_from_paragraphs(output_cfg, source_content, cfg)

    builder = _PROMPT_BUILDERS.get(output_type)
    if not builder:
        log(f"  ⚠ Unknown output type: {output_type}")
        return None

    if source_content is not None:
        prompt = builder(output_cfg, results_data, cfg, previous_narratives, source_content=source_content)
    else:
        prompt  = builder(output_cfg, results_data, cfg, previous_narratives)
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": 4000}
    }).encode("utf-8")

    try:
        req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=payload)
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=300) as resp:
            data    = json.loads(resp.read().decode())
            content = data.get("message", {}).get("content", "").strip()
            if content:
                log(f"  ✅ {output_type}: {len(content)} chars")
                return content
            log(f"  ⚠ AI returned empty response for {output_type}")
            return None
    except Exception as e:
        log(f"  ⚠ AI {output_type} failed: {e}")
        return None





def mock_output(output_cfg, cfg):
    output_type = output_cfg.get("type", "narrative")
    if output_type == "tweet":
        return f"[MOCK TWEET] Key story in {cfg['ai_topic']}: major development spotted, more details emerging. Watch this space."
    if output_type == "thread":
        num_posts = output_cfg.get("num_posts", 3)
        posts = [f"{i+1}/{num_posts} [MOCK] Thread post {i+1} covering a key story in {cfg['ai_topic']}." for i in range(num_posts)]
        posts[-1] += f" #MockHashtag #{cfg['ai_topic'].replace(' ', '')}"
        return "\n---\n".join(posts)
    return (
        f"[MOCK NARRATIVE] This is a test narrative for {cfg['ai_topic']}. "
        "In a real run, Ollama would generate several paragraphs of analysis here.\n\n"
        "A second paragraph would discuss trends and key players.\n\n"
        "Watch for real data when you run this on the Mac Mini."
    )
