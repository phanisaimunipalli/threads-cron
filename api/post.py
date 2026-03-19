"""
Vercel serverless function — generates and posts to Threads daily.
Triggered by Vercel Cron at 7:30 AM PST.
"""

import os
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler


# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.1-flash-lite-preview"

THREADS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN")
THREADS_USER_ID = os.environ.get("THREADS_USER_ID")
THREADS_API = "https://graph.threads.net/v1.0"

CRON_SECRET = os.environ.get("CRON_SECRET", "")


# ── Pillar rotation ───────────────────────────────────────────────────────────

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
- Practitioner-first (60%): Grounded observation, not theory. "Here's what I've noticed about X."
- Skeptic (25%): Earned contrarianism. "Everyone says X. The real answer is Y."
- Storyteller (15%): Open with tension or a scenario. Use sparingly.

ALWAYS:
- Write like you're talking to a smart peer, not an audience
- Lead with the most interesting thing first
- Be specific: name tools, patterns, failure modes
- Defend claims in 1-2 tight sentences

NEVER:
- "I'm excited to share..." or "Here's what most people get wrong..."
- Hashtag spam (max 1, often none)
- Motivational filler ("consistency is key", "trust the process")
- Reference specific employers, internal data, or scale numbers
- Words like "game-changer", "revolutionary", "unlock", "supercharge"
- Sound like a LinkedIn post or newsletter

FORMAT:
- Single post: 150-300 characters, line breaks for readability
- No emojis unless they genuinely add meaning (rare)"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_today_pillar():
    pst = timezone(timedelta(hours=-8))
    weekday = datetime.now(pst).weekday()
    return PILLARS[weekday]


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


def generate_content(pillar):
    headlines = fetch_hn_headlines()
    headlines_str = "\n".join(f"- {h}" for h in headlines) if headlines else "No headlines available."

    prompt = f"""{VOICE_PROMPT}

Today's content pillar: {pillar['name']}
Focus: {pillar['focus']}

Recent tech/AI headlines for context (use as inspiration, not to summarize):
{headlines_str}

Write a single Threads post (150-300 characters). Pick the format that fits best:
- Hot take: bold claim + 1-2 sentence defense
- Learning: observation → why it matters → implication
- Comparison: common approach vs. what actually breaks

Output only the post text, nothing else."""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.8}
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read())
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def _threads_post(url, data):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_to_threads(text):
    # Step 1: create container
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads", {
        "media_type": "TEXT",
        "text": text,
        "access_token": THREADS_TOKEN,
    })
    creation_id = result["id"]
    time.sleep(2)

    # Step 2: publish
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": creation_id,
        "access_token": THREADS_TOKEN,
    })
    return result["id"]


# ── Vercel handler ────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        # Verify cron secret to prevent unauthorized triggers
        auth = self.headers.get("authorization", "")
        if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
            self._respond(401, {"error": "Unauthorized"})
            return

        try:
            pillar = get_today_pillar()
            content = generate_content(pillar)
            thread_id = post_to_threads(content)

            self._respond(200, {
                "ok": True,
                "pillar": pillar["name"],
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
