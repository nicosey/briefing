import json
import urllib.request

from config import OLLAMA_URL, OLLAMA_MODEL, log


def generate_narrative(results_data, cfg, previous_narratives=None):
    results_text = ""
    for section in results_data:
        results_text += f"\n{section['section']}:\n"
        for r in section["results"]:
            results_text += f"- {r['title']}"
            if r["snippet"]:
                results_text += f": {r['snippet']}"
            results_text += "\n"

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

    prompt = f"""/no_think
You are {cfg['ai_persona']}.
Based on today's news below, write a concise, engaging narrative summary called "{cfg['ai_topic']}".

Rules:
- Write 3-4 short paragraphs maximum
- Lead with the most important story
- Mention key companies and deals
- Add brief analysis on what trends you see
- Keep it under 500 words
- Write in a professional but accessible tone
- Do NOT use markdown formatting, just plain text
- End with one sentence on what to watch next
{agg_instruction}
{history_block}TODAY'S RAW NEWS DATA:
{results_text}

Write the narrative now:"""

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
            data = json.loads(resp.read().decode())
            content = data.get("message", {}).get("content", "").strip()
            if content:
                log(f"  ✅ AI narrative: {len(content)} chars")
                return content
            log("  ⚠ AI returned empty response")
            return None
    except Exception as e:
        log(f"  ⚠ AI narrative failed: {e}")
        return None


def mock_narrative(cfg):
    return (
        f"[MOCK NARRATIVE] This is a test narrative for {cfg['ai_topic']}. "
        "In a real run, Ollama would generate several paragraphs of analysis here. "
        "The formatting, delivery, and message splitting are all exercised in mock mode.\n\n"
        "A second paragraph would discuss trends and key players. "
        "This confirms the full pipeline is working end-to-end on your laptop.\n\n"
        "Watch for real data when you run this on the Mac Mini."
    )
