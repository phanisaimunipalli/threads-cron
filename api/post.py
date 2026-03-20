"""
Vercel serverless function — generates and posts to Threads.
Triggered 3x/day by GitHub Actions at 7:30 AM, 12:30 PM, 6:30 PM PST.
"""

import os
import json
import time
import hashlib
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler


# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL    = "gemini-3.1-flash-lite-preview"

THREADS_TOKEN   = os.environ.get("THREADS_ACCESS_TOKEN")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID")
THREADS_API     = "https://graph.threads.net/v1.0"

CRON_SECRET     = os.environ.get("CRON_SECRET", "")


# ── Pillars ───────────────────────────────────────────────────────────────────

PILLARS = {
    0: {"name": "AI & Agents",        "focus": "Real agent behavior, failure modes, what's actually useful vs. hype"},
    1: {"name": "Product Management", "focus": "Decisions, prioritization, what data tells you vs. doesn't"},
    2: {"name": "Startups",           "focus": "Founder-PM dynamics, build decisions, what scales vs. doesn't"},
    3: {"name": "Technology",         "focus": "Tools, architectures, developer observations, infra patterns"},
    4: {"name": "Intersection",       "focus": "Where AI meets PM meets product decisions"},
    5: {"name": "Contrarian Take",    "focus": "One thing the internet gets wrong this week"},
    6: {"name": "Long-form Thread",   "focus": "Deep-dive on one important topic, 5-10 posts"},
}

VOICE_PROMPT = """You are writing Threads posts for a senior product manager and technologist.

VOICE RULES:
- Practitioner-first (60%): Grounded observation, not theory. "I've noticed X."
- Skeptic (25%): Earned contrarianism. "Everyone says X. The real answer is Y."
- Storyteller (15%): Open with tension or a scenario. Use sparingly.

ALWAYS:
- Open with "I" perspective when possible. First-person lands harder.
- Create a tension gap in the first line. Make the reader need to know what comes next.
- Write like a group chat with a smart friend, not a newsletter.
- Use contractions (isn't, you're, that's). Sound human.
- Be specific: name tools, patterns, failure modes.

NEVER:
- Use dashes ( - ) anywhere. Not hyphens, not em dashes. Use a period or new line instead.
- "I'm excited to share..." or "Here's what most people get wrong..."
- Hashtag spam (max 1, often none)
- Motivational filler ("consistency is key", "trust the process")
- Reference specific employers, internal data, or scale numbers
- Words like "game-changer", "revolutionary", "unlock", "supercharge"
- Sound like a LinkedIn post or newsletter

FORMAT:
- 150-300 characters, line breaks for readability
- No emojis unless they genuinely add meaning (rare)"""

FORMATS = [
    {
        "name": "short_punchy",
        "instruction": "Write a SHORT post (100-200 characters). One bold claim. Two tight sentences max. Each line hits hard. No filler."
    },
    {
        "name": "dense_long",
        "instruction": "Write a LONGER dense post (300-500 characters). No line breaks. One continuous paragraph. Pack in the insight. Write like you're explaining something to a smart friend in a message."
    },
    {
        "name": "tension_story",
        "instruction": "Open with a scene or a moment. One sentence. Then unpack what it revealed. 3-5 short lines. End with the insight, not a call to action."
    },
    {
        "name": "contrarian",
        "instruction": "State the thing everyone believes. Then immediately contradict it with what you actually know. Keep it under 250 characters. No hedging."
    },
]


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini(prompt, temperature=0.8):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 500, "temperature": temperature}
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read())
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Content ───────────────────────────────────────────────────────────────────

def fetch_hn_headlines(n=5):
    try:
        with urllib.request.urlopen("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=5) as r:
            ids = json.loads(r.read())[:20]
        titles = []
        for story_id in ids:
            try:
                with urllib.request.urlopen(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=3) as r:
                    item = json.loads(r.read())
                    if item.get("title"):
                        titles.append(item["title"])
                if len(titles) >= n:
                    break
            except Exception:
                continue
        return titles
    except Exception:
        return []


def get_today_pillar():
    pst = timezone(timedelta(hours=-8))
    weekday = datetime.now(pst).weekday()
    return PILLARS[weekday]


def refine_draft(draft):
    prompt = f"""You are a Threads engagement editor. Make this post land harder.

Original post:
\"\"\"{draft}\"\"\"

Rules:
- Rewrite the opening line to create tension or curiosity. It must stop the scroll.
- Tighten every line. Cut filler. Remove anything that doesn't earn its place.
- Keep the core insight and voice intact.
- Open with "I" if it fits naturally.
- Stay under 300 characters total.
- No emojis, no hashtags, no LinkedIn tone.
- CRITICAL: Never use dashes ( - ) anywhere. Use a period or line break instead.

Output only the rewritten post, nothing else."""
    return _gemini(prompt, temperature=0.7)


def generate_content(pillar, post_number=0):
    headlines = fetch_hn_headlines()
    headlines_str = "\n".join(f"- {h}" for h in headlines) if headlines else "No headlines available."
    fmt = FORMATS[post_number % len(FORMATS)]

    prompt = f"""{VOICE_PROMPT}

Today's content pillar: {pillar['name']}
Focus: {pillar['focus']}

Recent tech/AI headlines for context (use as inspiration, not to summarize):
{headlines_str}

Format: {fmt['name']}
{fmt['instruction']}

CRITICAL: Never use dashes ( - ) anywhere in the post.
Output only the post text, nothing else."""

    draft = _gemini(prompt)
    return refine_draft(draft), fmt["name"]


# ── Threads ───────────────────────────────────────────────────────────────────

def _threads_post(url, data):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_to_threads(text):
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads", {
        "media_type": "TEXT",
        "text": text,
        "access_token": THREADS_TOKEN,
    })
    time.sleep(2)
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": result["id"],
        "access_token": THREADS_TOKEN,
    })
    return result["id"]


# ── Handler ───────────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        auth = self.headers.get("authorization", "")
        if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
            self._respond(401, {"error": "Unauthorized"})
            return

        try:
            pillar = get_today_pillar()
            hour = datetime.now(timezone.utc).hour
            post_number = 0 if hour < 18 else (1 if hour < 22 else 2)

            content, fmt_name = generate_content(pillar, post_number)
            thread_id = post_to_threads(content)

            self._respond(200, {
                "ok": True,
                "pillar": pillar["name"],
                "format": fmt_name,
                "thread_id": thread_id,
                "content": content,
            })
        except Exception as e:
            self._respond(500, {"ok": False, "error": str(e)})

    def _respond(self, status, body):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))

    def log_message(self, *args):
        pass
