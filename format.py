from datetime import datetime

from config import OLLAMA_MODEL


def truncate(text, max_len=120):
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] + "…"


def build_raw_briefing(results_data, cfg):
    now = datetime.now()
    header = (
        f'{cfg["header_emoji"]} <b>{cfg["title"].upper()}</b>\n'
        f'📅 {now.strftime("%A, %d %B %Y")} • {now.strftime("%H:%M")}\n'
        f'{"─" * 30}'
    )
    sections = [header]
    for s in results_data:
        section = f'\n{s["emoji"]} <b>{s["section"]}</b>\n'
        if s["results"]:
            for r in s["results"]:
                section += f'• <b>{r["title"]}</b>'
                if r["snippet"]:
                    section += f'\n  <i>{truncate(r["snippet"])}</i>'
                if r["url"]:
                    section += f'\n  <a href="{r["url"]}">→ Read</a>'
                section += "\n"
        else:
            section += "  <i>No results found today</i>\n"
        sections.append(section)
    sections.append(f'\n{"─" * 30}\n{cfg["footer_emoji"]} <i>SearXNG • {len(results_data)} searches</i>')
    return "\n".join(sections)


def build_output_message(content, output_cfg, cfg):
    """Format a generated output for delivery. Dispatches by output type."""
    output_type = output_cfg.get("type", "narrative")

    if output_type == "tweet":
        return f'{cfg["header_emoji"]} {content}'

    # narrative (default)
    now = datetime.now()
    return (
        f'{cfg["header_emoji"]} <b>{cfg["ai_topic"].upper()}</b>\n'
        f'📅 {now.strftime("%A, %d %B %Y")}\n'
        f'{"─" * 30}\n\n'
        f'{content}\n\n'
        f'{"─" * 30}\n'
        f'🧠 <i>Written by {OLLAMA_MODEL}</i>'
    )
