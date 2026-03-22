"""
Vercel serverless function — generates and posts to Threads.
Triggered 3x/day by GitHub Actions at 7:30 AM, 12:30 PM, 6:30 PM PST.
Strategy: Mental Model + Real Company Story + Data. One week test.
"""

import os
import json
import time
import re
import random
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


# ── Mental Models Bank ────────────────────────────────────────────────────────
# Model name + definition only. Gemini picks a fresh company example each time.
# This prevents the same post being generated repeatedly from hardcoded stories.

MENTAL_MODELS = [
    {"model": "Working Backwards", "what": "Write the press release before writing any code. Forces clarity on who benefits and why before a single decision is locked in."},
    {"model": "Jobs To Be Done", "what": "People don't use products. They hire them to make progress in a specific situation. The job doesn't change. The product does."},
    {"model": "Minimum Viable Product", "what": "The smallest thing you can ship that tests your most critical assumption. Not the smallest thing you can build."},
    {"model": "North Star Metric", "what": "One number that represents the core value you deliver to users. Everything else is a leading indicator or a distraction."},
    {"model": "Flywheel Effect", "what": "A self-reinforcing loop where each part of the system makes the next part easier. Hard to start. Very hard to stop."},
    {"model": "Pre-mortem", "what": "Before you launch, assume the project already failed. Work backwards to find out exactly why."},
    {"model": "Second-Order Thinking", "what": "First-order thinking asks what happens next. Second-order thinking asks what happens after that, and who adapts."},
    {"model": "Inversion", "what": "Don't ask how to make a great product. Ask what would make this product terrible, then systematically eliminate those things."},
    {"model": "Loss Aversion", "what": "People feel losses roughly twice as intensely as equivalent gains. Design for what users stand to lose, not just what they'll gain."},
    {"model": "Anchoring", "what": "The first number a person sees shapes every judgment that follows. In product, the anchor is almost always set before the price conversation starts."},
    {"model": "Dogfooding", "what": "Use your own product before shipping it to customers. Not as a test. As your primary workflow."},
    {"model": "Pareto Principle in Product", "what": "80% of the value your product delivers comes from 20% of its features. The rest is maintenance overhead masquerading as product strategy."},
    {"model": "Occam's Razor in Specs", "what": "When two product solutions solve the same problem, the simpler one is almost always better. Not because it's easier to build. Because it's easier for users to trust."},
    {"model": "Probabilistic Roadmaps", "what": "Don't predict which feature will win. Model a portfolio of bets where the expected value across all of them justifies the investment."},
    {"model": "The Rule of Three in Product Writing", "what": "Every product document should answer three questions and only three: what is the problem, who has it, and what changes for them when it's solved."},
    {"model": "Opportunity Scoring", "what": "Prioritize by importance minus satisfaction. If users say a job is critical but no product does it well, that's your opening."},
    {"model": "Type 1 vs Type 2 Decisions", "what": "Reversible decisions should be made fast and low in the org. Irreversible decisions deserve more time and more people. Conflating them is how teams get slow."},
    {"model": "Narrative Fallacy in Specs", "what": "Humans are pattern-completers. A well-written product story can make a bad bet feel inevitable. Be suspicious of specs that read too cleanly."},
    {"model": "The Curse of Knowledge in Product Writing", "what": "The more you know about your product, the harder it is to write about it for someone who doesn't. Expertise is the enemy of clarity."},
    {"model": "Shape Up: Fixed Time, Variable Scope", "what": "Fix the time, flex the scope. A 6-week cycle with a flexible problem statement ships more than an infinite sprint with a fixed spec."},
    {"model": "Regret Minimization in Product Decisions", "what": "When deciding whether to build something, ask: will I regret not doing this when I'm looking back in 10 years?"},
    {"model": "Adjacent Possible in Product Strategy", "what": "Every product can only move one step into what's adjacent to what users already understand. Skip a step and they can't follow."},
    {"model": "Compound Improvement in Product Quality", "what": "Small quality improvements compound. A 1% better retention rate, compounded monthly, becomes a structurally different product in 18 months."},
    {"model": "Scarcity and Urgency", "what": "People want what they can't easily have. Perceived scarcity drives urgency even when supply is artificial."},
]


# ── Voice ─────────────────────────────────────────────────────────────────────

VOICE_PROMPT = """You are writing Threads posts for a senior product manager and technologist.

VOICE RULES:
- Practitioner-first: "I've noticed X." Grounded observation, not theory.
- Skeptic: "Everyone says X. The real answer is Y." Earned contrarianism.
- Write like a group chat with a smart friend, not a newsletter.
- Use contractions (isn't, you're, that's). Sound human.

ALWAYS:
- Open with "I" perspective when possible. First-person lands harder.
- Create a tension gap in the first line. Make the reader need to know what's next.
- Name the company, name the product, name the outcome. Be specific.
- Ground claims in numbers when you can.

NEVER:
- Use dashes ( - ) anywhere. Not hyphens, not em dashes. Use a period or new line.
- Sound like LinkedIn, a newsletter, or a textbook.
- Use: "game-changer", "revolutionary", "unlock", "supercharge", "leverage"
- Hashtag spam (zero or one max)
- Motivational filler of any kind"""


# ── Sources ───────────────────────────────────────────────────────────────────

def fetch_techcrunch_ai(n=4):
    try:
        url = "https://techcrunch.com/category/artificial-intelligence/feed/"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            content = r.read().decode("utf-8")
        titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>", content)
        titles = [t for t in titles if "TechCrunch" not in t]
        return titles[:n]
    except Exception:
        return []


def fetch_hn_headlines(n=4):
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


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini(prompt, temperature=0.8):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 600, "temperature": temperature}
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as r:
        result = json.loads(r.read())
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


# ── Content generation ────────────────────────────────────────────────────────

def pick_mental_model(post_number):
    """
    Cycle through mental models without repeating within a full cycle.
    Each complete cycle uses a different shuffle order, so the same model
    never appears in the same position across consecutive cycles.
    """
    n = len(MENTAL_MODELS)
    cycle = post_number // n          # which full cycle we're in
    position = post_number % n        # position within this cycle
    rng = random.Random(cycle)        # deterministic but different each cycle
    indices = list(range(n))
    rng.shuffle(indices)
    return MENTAL_MODELS[indices[position]]


def get_post_number():
    """Unique index per post slot across the year. 3 slots per day."""
    now = datetime.now(timezone.utc)
    day_of_year = now.timetuple().tm_yday
    hour = now.hour
    # Slot 0 = 7:30 AM PST (15:30 UTC), Slot 1 = 12:30 PM PST (20:30 UTC), Slot 2 = 6:30 PM PST (02:30 UTC next day)
    slot = 0 if hour < 19 else (1 if hour < 23 else 2)
    return (day_of_year - 1) * 3 + slot


def refine_draft(draft):
    prompt = f"""You are a Threads engagement editor. This account's niche is: mental models + product thinking + data.

Original post:
\"\"\"{draft}\"\"\"

Rules:
- Rewrite the opening line so a product thinker stops scrolling immediately.
- Every post must have all three elements: a named mental model, a product decision, and real data.
- If the data is missing or vague, sharpen it. The number must land.
- The insight must be something a PM can apply this week, not a general observation.
- Tighten every line. Remove anything that doesn't earn its place.
- Stay under 400 characters total.
- No emojis, no hashtags, no LinkedIn tone, no motivational filler.
- CRITICAL: Never use dashes ( - ) anywhere. Use a period or line break instead.

Output only the rewritten post, nothing else."""
    return _gemini(prompt, temperature=0.7)


def generate_content(post_number=0):
    mm = pick_mental_model(post_number)
    tc = fetch_techcrunch_ai(3)
    hn = fetch_hn_headlines(3)
    headlines = tc + hn
    headlines_str = "\n".join(f"- {h}" for h in headlines) if headlines else ""

    prompt = f"""{VOICE_PROMPT}

NICHE: Mental models + product thinking + data.
Every post must: name the mental model, show a real product company using it, end with real data.
Never use the same company example twice in a row. Pick a fresh, specific example each time.
Do not default to Amazon, Apple, or Netflix unless the example is genuinely the best one.

Today's mental model:
Model: {mm['model']}
What it is: {mm['what']}

Your job:
1. Pick a real product company or team that applied this mental model to a product decision. Be specific. Not the most obvious example.
2. Explain exactly what they did. Name the product, the decision, the moment.
3. End with real outcome data. A number that proves it worked or failed.
4. Optional: one line the reader can apply this week.

{f"Recent context (use only if it genuinely fits):{chr(10)}{headlines_str}" if headlines_str else ""}

Keep it under 400 characters. No filler. No motivation. No dashes anywhere.
Output only the post text, nothing else."""

    draft = _gemini(prompt)
    return refine_draft(draft), mm["model"]


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
            post_number = get_post_number()
            content, model_name = generate_content(post_number)
            thread_id = post_to_threads(content)

            self._respond(200, {
                "ok": True,
                "model": model_name,
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
