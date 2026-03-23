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
{agg_instruction}
{history_block}TODAY'S RAW NEWS DATA:
{_results_text(results_data)}

Write the narrative now:"""


def _tweet_prompt(output_cfg, results_data, cfg):
    max_chars = output_cfg.get("max_chars", 280)
    return f"""/no_think
You are {cfg['ai_persona']}.
Based on today's news below, write a single tweet-sized summary of the most important story.

Rules:
- Maximum {max_chars} characters including spaces
- Lead with the biggest story
- Plain text only, no hashtags, no markdown
- One or two sentences maximum

TODAY'S RAW NEWS DATA:
{_results_text(results_data)}

Write the tweet now:"""


# ── prompt registry ──────────────────────────────────────────
# To add a new output type: add an entry here returning a prompt string.

_PROMPT_BUILDERS = {
    "narrative": _narrative_prompt,
    "tweet":     lambda cfg_out, rd, cfg, prev: _tweet_prompt(cfg_out, rd, cfg),
}


# ── public API ───────────────────────────────────────────────

def generate_output(output_cfg, results_data, cfg, previous_narratives=None):
    output_type = output_cfg.get("type", "narrative")
    builder = _PROMPT_BUILDERS.get(output_type)
    if not builder:
        log(f"  ⚠ Unknown output type: {output_type}")
        return None

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
    return (
        f"[MOCK NARRATIVE] This is a test narrative for {cfg['ai_topic']}. "
        "In a real run, Ollama would generate several paragraphs of analysis here.\n\n"
        "A second paragraph would discuss trends and key players.\n\n"
        "Watch for real data when you run this on the Mac Mini."
    )
