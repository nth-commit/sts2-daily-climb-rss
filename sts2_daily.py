#!/usr/bin/env python3
"""Slay the Spire 2 daily challenge generator + RSS feed writer.

There is no daily-challenge API. The game derives the daily from the UTC date,
so this script computes it locally with no network calls.

The lists below must be updated if a game patch adds characters or modifiers.

Usage:
  python3 sts2_daily.py                      # print today's daily
  python3 sts2_daily.py --date 2026-10-31    # print a past day (future dates are rejected)
  python3 sts2_daily.py --rss feed.xml       # write an RSS feed of the last 14 days
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from email.utils import format_datetime
from xml.sax.saxutils import escape

M64 = (1 << 64) - 1
M32 = (1 << 32) - 1

# --- Game data (order matters) ----------------------------------------------

CHARACTERS = ["IRONCLAD", "SILENT", "REGENT", "NECROBINDER", "DEFECT"]

GOOD_MODIFIERS = [
    "DRAFT", "SEALED_DECK", "HOARDER", "SPECIALIZED", "INSANITY",
    "ALL_STAR", "FLIGHT", "VINTAGE", "CHARACTER_CARDS",
]
BAD_MODIFIERS = [
    "DEADLY_EVENTS", "CURSED_RUN", "BIG_GAME_HUNTER", "MIDAS",
    "MURDEROUS", "NIGHT_TERRORS", "TERMINAL",
]
MUTUALLY_EXCLUSIVE = [{"SEALED_DECK", "DRAFT", "INSANITY"}]

# --- Display text (names from the game, summaries paraphrased) --------------

CHARACTER_NAMES = {
    "IRONCLAD": "The Ironclad", "SILENT": "The Silent", "REGENT": "The Regent",
    "NECROBINDER": "The Necrobinder", "DEFECT": "The Defect",
}
MODIFIER_TEXT = {
    "ALL_STAR": ("All Star", "Your starting deck includes 5 colorless cards."),
    "BIG_GAME_HUNTER": ("Big Game Hunter", "More Elites appear, and they give better rewards."),
    "CURSED_RUN": ("Cursed Run", "Gain a random Curse at the start of every Act."),
    "DEADLY_EVENTS": ("Deadly Events", "Unknown rooms may hold Elites, but Treasure is also more common there."),
    "DRAFT": ("Draft", "Build your starting deck by picking from 10 card rewards."),
    "FLIGHT": ("Flight", "Travel to any room on the next floor, regardless of paths."),
    "HOARDER": ("Hoarder", "Every card you add comes with 2 extra copies. The Merchant won't remove cards."),
    "INSANITY": ("Insanity", "Your starting deck is 30 random cards."),
    "MIDAS": ("Midas", "Enemies give triple gold, but you can't upgrade cards at Rest Sites."),
    "MURDEROUS": ("Murderous", "You and every enemy start each combat with 3 Strength."),
    "NIGHT_TERRORS": ("Night Terrors", "Resting fully heals you but lowers your Max HP by 5."),
    "SEALED_DECK": ("Sealed Deck", "Pick 10 of 30 cards to form your starting deck."),
    "SPECIALIZED": ("Specialized", "Your starting deck includes 5 copies of one card."),
    "TERMINAL": ("Terminal", "Lose 1 Max HP on entering each room. Start every combat with 5 Plating."),
    "VINTAGE": ("Vintage", "Normal fights reward relics in place of cards."),
}
ASCENSION_TITLES = [
    "No Ascension", "Swarming Elites", "Weary Traveler", "Poverty", "Tight Belt",
    "Ascender's Bane", "Inflation", "Scarcity", "Tough Enemies", "Deadly Enemies", "Double Boss",
]


# --- RNG --------------------------------------------------------------------

def _rotl(x: int, k: int) -> int:
    return ((x << k) | (x >> (64 - k))) & M64


class Xoshiro256:
    """xoshiro256** seeded with splitmix64."""

    def __init__(self, seed: int):
        x = seed & M64
        state = []
        for _ in range(4):
            x = (x + 0x9E3779B97F4A7C15) & M64
            z = x
            z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & M64
            z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & M64
            state.append(z ^ (z >> 31))
        self.s = state

    def next_ulong(self) -> int:
        s0, s1, s2, s3 = self.s
        result = (_rotl((s1 * 5) & M64, 7) * 9) & M64
        t = (s1 << 17) & M64
        s2 ^= s0
        s3 ^= s1
        s1 ^= s2
        s0 ^= s3
        s2 ^= t
        s3 = _rotl(s3, 45)
        self.s = [s0, s1, s2, s3]
        return result

    def next_double(self) -> float:
        return (self.next_ulong() >> 11) * 1.1102230246251565e-16


class Rng:
    """Seeded RNG with the helpers the daily uses."""

    def __init__(self, seed: int):
        self._r = Xoshiro256(seed & M32)

    def next_int(self, lo: int, hi: int | None = None) -> int:
        if hi is None:
            lo, hi = 0, lo
        return int(self._r.next_double() * (hi - lo)) + lo

    def next_uint(self) -> int:
        return int(self._r.next_double() * float(M32)) & M32

    def next_item(self, items: list):
        return items[self.next_int(0, len(items))] if items else None

    def shuffle(self, items: list) -> list:
        n = len(items)
        while n > 1:
            n -= 1
            k = self.next_int(n + 1)
            items[k], items[n] = items[n], items[k]
        return items


def deterministic_hash(s: str) -> int:
    """Deterministic string hash using 32-bit signed arithmetic."""
    def i32(v: int) -> int:
        v &= M32
        return v - (1 << 32) if v & 0x80000000 else v

    a = b = 352654597
    for i in range(0, len(s), 2):
        a = i32(((a << 5) + a) ^ ord(s[i]))
        if i == len(s) - 1:
            break
        b = i32(((b << 5) + b) ^ ord(s[i + 1]))
    return i32(a + b * 1566083941)


# --- Daily generation -------------------------------------------------------

def utc_today(lead_hours: int = 0) -> dt.date:
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=lead_hours)).date()


def generate_daily(date: dt.date, players: int = 1) -> dict:
    date_str = date.strftime("%d_%m_%Y")
    rng = Rng(deterministic_hash(date_str) & M32)
    char_rng = Rng(rng.next_uint())
    asc_rng = Rng(rng.next_uint())
    mod_rng = Rng(rng.next_uint())

    characters = [char_rng.next_item(CHARACTERS) for _ in range(players)]
    ascension = asc_rng.next_int(0, 11)

    modifiers = []
    # The good-modifier pool is sorted by ID before it is shuffled.
    pool = mod_rng.shuffle(sorted(GOOD_MODIFIERS))
    for _ in range(2):
        mod = mod_rng.next_item(pool)
        if mod is None:
            raise RuntimeError("There were not enough good modifiers to fill the daily!")
        entry = {"id": mod}
        if mod == "CHARACTER_CARDS":
            # Character Cards never picks the daily character.
            entry["character"] = mod_rng.next_item([c for c in CHARACTERS if c not in characters])
        modifiers.append(entry)
        pool.remove(mod)
        for group in MUTUALLY_EXCLUSIVE:
            if mod in group:
                pool = [m for m in pool if m not in group]
    modifiers.append({"id": mod_rng.next_item(BAD_MODIFIERS)})

    return {
        "date": date.isoformat(),
        "seed": f"{date_str}_{players}P",
        "character": characters[0],
        "characters": characters,
        "ascension": ascension,
        "modifiers": modifiers,
    }


def describe_modifier(m: dict) -> tuple[str, str]:
    if m["id"] == "CHARACTER_CARDS":
        name = m["character"].title()
        return f"{name} Cards", f"{name} cards can show up in rewards and shops."
    return MODIFIER_TEXT.get(m["id"], (m["id"].replace("_", " ").title(), ""))


# --- Output -----------------------------------------------------------------

def format_text(d: dict) -> str:
    lines = [
        f"Slay the Spire 2 daily: {d['date']} (seed {d['seed']})",
        f"Character: {CHARACTER_NAMES[d['character']]}",
        f"Ascension: {d['ascension']} ({ASCENSION_TITLES[d['ascension']]})",
        "Modifiers:",
    ]
    for m in d["modifiers"]:
        title, desc = describe_modifier(m)
        lines.append(f"  - {title}: {desc}")
    return "\n".join(lines)


def rss_item(d: dict, site_url: str, repost_at: dt.datetime | None = None) -> str:
    """One feed item. With repost_at, the item gets a one-off guid, link and pubDate
    so Slack treats it as new and posts it to the channel again."""
    char = CHARACTER_NAMES[d["character"]]
    mods = [describe_modifier(m) for m in d["modifiers"]]
    title = f"{d['date']}: {char}, A{d['ascension']}, " + " / ".join(t for t, _ in mods)
    # Slack's RSS app strips HTML tags but turns <br/> into line breaks.
    lines = [
        f"Character: {escape(char)}",
        f"Ascension: {d['ascension']} ({escape(ASCENSION_TITLES[d['ascension']])})",
        "Modifiers:",
    ] + [f"• {escape(t)}: {escape(desc)}" for t, desc in mods]
    body = "<br/>".join(lines)
    day = dt.date.fromisoformat(d["date"])
    guid = f"sts2-daily-{d['date']}"
    link = f"{site_url}#{d['date']}"
    published = dt.datetime(day.year, day.month, day.day, tzinfo=dt.timezone.utc)
    if repost_at:
        stamp = repost_at.strftime("%Y%m%dT%H%M%S")
        guid += f"-repost-{stamp}"
        link = f"{site_url}?repost={stamp}#{d['date']}"
        published = repost_at
    pub = format_datetime(published)
    return (
        "<item>"
        f"<title>{escape(title)}</title>"
        f"<link>{escape(link)}</link>"
        f"<guid isPermaLink=\"false\">{guid}</guid>"
        f"<pubDate>{pub}</pubDate>"
        f"<description><![CDATA[{body}]]></description>"
        "</item>"
    )


def recent_dailies(today: dt.date, days: int) -> list[dict]:
    return [generate_daily(today - dt.timedelta(days=i)) for i in range(days)]


def build_rss(today: dt.date, days: int, site_url: str, repost: bool = False) -> str:
    dailies = recent_dailies(today, days)
    items = [rss_item(d, site_url) for d in dailies]
    now_dt = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    if repost:
        items.insert(0, rss_item(dailies[0], site_url, repost_at=now_dt))
    now = format_datetime(now_dt)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>'
        "<title>Slay the Spire 2 Daily Challenge</title>"
        f"<link>{escape(site_url)}</link>"
        "<description>Character, ascension and modifiers for each Slay the Spire 2 daily run. Resets at 00:00 UTC.</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        "<ttl>60</ttl>"
        + "".join(items)
        + "</channel></rss>\n"
    )


HTML_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>STS2 Daily Climb</title>
<link rel="alternate" type="application/rss+xml" title="Slay the Spire 2 Daily Challenge" href="feed.xml">
<style>
  :root {{ --bg: #f7f5f2; --card: #fff; --text: #1d1b19; --muted: #6b6560; --accent: #b3402a; --border: #e4dfd8; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg: #161412; --card: #201d1a; --text: #ece7e1; --muted: #a39b93; --accent: #e0745c; --border: #34302c; }}
  }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, sans-serif; }}
  main {{ max-width: 720px; margin: 0 auto; padding: 32px 16px; }}
  h1 {{ margin: 0 0 4px; font-size: 1.6rem; }}
  .sub {{ color: var(--muted); margin: 0 0 24px; }}
  a {{ color: var(--accent); }}
  article {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 12px; scroll-margin-top: 16px; }}
  article:target {{ border-color: var(--accent); }}
  h2 {{ margin: 0 0 8px; font-size: 1.05rem; }}
  h2 a {{ color: inherit; text-decoration: none; }}
  .meta {{ margin: 0 0 8px; }}
  ul {{ margin: 0; padding-left: 20px; }}
  li span {{ color: var(--muted); }}
</style>
</head>
<body>
<main>
<h1>Slay the Spire 2 Daily Climb</h1>
<p class="sub">Character, ascension and modifiers for each daily run. Resets at 00:00 UTC. <a href="feed.xml">RSS feed</a></p>
{articles}
</main>
</body>
</html>
"""


def html_article(d: dict) -> str:
    char = CHARACTER_NAMES[d["character"]]
    mods = "".join(
        f"<li><b>{escape(t)}</b> <span>{escape(desc)}</span></li>"
        for t, desc in map(describe_modifier, d["modifiers"])
    )
    return (
        f'<article id="{d["date"]}">'
        f'<h2><a href="#{d["date"]}">{d["date"]}</a></h2>'
        f'<p class="meta">{escape(char)} · Ascension {d["ascension"]} ({escape(ASCENSION_TITLES[d["ascension"]])})</p>'
        f"<ul>{mods}</ul>"
        "</article>"
    )


def build_html(today: dt.date, days: int) -> str:
    return HTML_PAGE.format(articles="\n".join(html_article(d) for d in recent_dailies(today, days)))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--date", help="UTC date YYYY-MM-DD, today or earlier (default: today in UTC)")
    p.add_argument("--json", action="store_true", help="print JSON")
    p.add_argument("--rss", metavar="PATH", help="write an RSS feed to PATH")
    p.add_argument("--html", metavar="PATH", help="write an HTML page of recent dailies to PATH")
    p.add_argument("--days", type=int, default=14, help="days in the RSS feed and HTML page (default 14)")
    p.add_argument("--repost", action="store_true",
                   help="add a copy of the latest daily with a one-off ID so Slack posts it again")
    p.add_argument("--site-url", default="https://nth-commit.github.io/sts2-daily-climb-rss/",
                   help="URL of the HTML page; feed items link to <site-url>#<date>")
    # Used by the scheduled workflow so the feed is ready before the daily resets.
    p.add_argument("--lead-hours", type=int, default=0, help=argparse.SUPPRESS)
    args = p.parse_args()
    if not 0 <= args.lead_hours <= 24:
        p.error("--lead-hours must be between 0 and 24")

    today = utc_today(args.lead_hours)
    day = dt.date.fromisoformat(args.date) if args.date else today
    if day > today:
        p.error(f"{day} is in the future (today is {today} UTC); future dailies are not shown")

    outputs = []
    if args.rss:
        outputs.append((args.rss, build_rss(day, args.days, args.site_url, args.repost)))
    if args.html:
        outputs.append((args.html, build_html(day, args.days)))
    for path, content in outputs:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Wrote {path} ({args.days} days ending {day})")
    if outputs:
        return 0

    d = generate_daily(day)
    print(json.dumps(d, indent=2) if args.json else format_text(d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
