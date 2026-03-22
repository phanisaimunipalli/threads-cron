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


# ── Mental Models (definitions only) ─────────────────────────────────────────

MENTAL_MODELS = [
    {"model": "Working Backwards", "what": "Write the press release before writing any code. Forces clarity on who benefits and why before a single decision is locked in."},
    {"model": "Jobs To Be Done", "what": "People don't use products. They hire them to make progress in a specific situation. The job doesn't change. The product does."},
    {"model": "Minimum Viable Product", "what": "The smallest thing that tests your most critical assumption. Not the smallest thing you can build."},
    {"model": "North Star Metric", "what": "One number that captures the core value you deliver. Everything else is a leading indicator or a distraction."},
    {"model": "Flywheel Effect", "what": "A self-reinforcing loop where each part makes the next part easier. Hard to start. Very hard to stop."},
    {"model": "Pre-mortem", "what": "Before you launch, assume the project already failed. Work backwards to find out exactly why."},
    {"model": "Second-Order Thinking", "what": "First-order thinking asks what happens next. Second-order thinking asks what happens after that, and who adapts."},
    {"model": "Inversion", "what": "Don't ask how to make a great product. Ask what would make it terrible, then systematically eliminate those things."},
    {"model": "Loss Aversion", "what": "People feel losses twice as intensely as equivalent gains. Design for what users stand to lose, not just what they'll gain."},
    {"model": "Anchoring", "what": "The first number a person sees shapes every judgment that follows. In product, the anchor is almost always set before the price conversation starts."},
    {"model": "Dogfooding", "what": "Use your own product before shipping it to customers. Not as a test. As your primary workflow."},
    {"model": "Pareto Principle in Product", "what": "80% of your product's value comes from 20% of its features. The rest is maintenance overhead masquerading as product strategy."},
    {"model": "Occam's Razor in Specs", "what": "When two solutions solve the same problem, the simpler one wins. Not because it's easier to build. Because users trust it faster."},
    {"model": "Probabilistic Roadmaps", "what": "Don't predict which feature wins. Build a portfolio of bets where the expected value across all of them justifies the investment."},
    {"model": "The Rule of Three in Product Writing", "what": "Every product doc should answer exactly three questions: what is the problem, who has it, what changes when it's solved."},
    {"model": "Opportunity Scoring", "what": "Prioritize by importance minus satisfaction. If users say a job is critical but no product does it well, that's your opening."},
    {"model": "Type 1 vs Type 2 Decisions", "what": "Reversible decisions should be made fast. Irreversible ones deserve more process. Conflating them is how teams get slow."},
    {"model": "Narrative Fallacy in Specs", "what": "A coherent product story can make a bad bet feel inevitable. Be suspicious of specs that read too cleanly."},
    {"model": "The Curse of Knowledge in Product Writing", "what": "The more you know about your product, the harder it is to write for someone who doesn't. Expertise kills clarity."},
    {"model": "Shape Up: Fixed Time, Variable Scope", "what": "Fix the time, flex the scope. A 6-week cycle with a variable problem ships more than infinite sprints with a fixed spec."},
    {"model": "Regret Minimization in Product Decisions", "what": "When deciding whether to build, ask: will I regret not doing this in 10 years? Most urgent roadmap debates look trivial from that view."},
    {"model": "Adjacent Possible in Product Strategy", "what": "Every product can only move one step into what users already understand. Skip a step and they can't follow."},
    {"model": "Compound Improvement in Product Quality", "what": "Small quality improvements compound. A 1% retention gain, compounded monthly, becomes a structurally different product in 18 months."},
    {"model": "Scarcity and Urgency", "what": "People want what they can't easily have. Artificial scarcity drives urgency even when supply is unlimited."},
]


# ── Company Pool (with real data facts for Gemini to use) ─────────────────────

COMPANIES = [
    {"name": "Stripe", "facts": "$95B valuation. Writing clarity is a core hiring signal. API-first. Developer docs ranked best-in-class year over year."},
    {"name": "Figma", "facts": "$400M ARR. Adobe acquisition offer at $10B. Real-time multiplayer was the core product bet. 4M+ designers."},
    {"name": "Linear", "facts": "$35M ARR. Team under 50. NPS above 70 in developer tooling. Speed and simplicity as stated product principles."},
    {"name": "Notion", "facts": "20M users. $10B valuation. Grew from near-zero in 5 years by targeting knowledge workers."},
    {"name": "Duolingo", "facts": "500M users. 37M DAU. Runs 500+ A/B tests per year. Streak users retain at 2x rate. DAU grew from 10M to 37M in 3 years."},
    {"name": "Superhuman", "facts": "$30/month for email. NPS of 58 vs Gmail's 1. Invite-only for 4 years. Built on rigorous user interview methodology."},
    {"name": "Basecamp", "facts": "Profitable 20+ years. Under 60 employees. 3 million companies. Invented Shape Up. No VC, no growth team."},
    {"name": "Intercom", "facts": "$150M ARR. Pioneer of Jobs to Be Done applied to B2B SaaS. Pivoted to AI-first customer support."},
    {"name": "Slack", "facts": "$7B ARR. Acquired by Salesforce for $27.7B. Started as internal tool at gaming company Tiny Speck."},
    {"name": "Shopify", "facts": "4M merchants. App ecosystem 8,000+ apps. Third-party developers earn 4x what Shopify earns from the platform."},
    {"name": "Airbnb", "facts": "100M nights booked annually. Near-bankrupt in 2009. North star metric was nights booked, not revenue."},
    {"name": "Spotify", "facts": "600M users. 30 min average daily listening. Runs bet-portfolio approach to product. Experiment velocity is a stated growth driver."},
    {"name": "Buffer", "facts": "Founded with landing page test before a single line of code. $20M ARR bootstrapped. Transparent salary model."},
    {"name": "GitHub", "facts": "100M developers. GitHub Actions used by 10M+. Acquired by Microsoft for $7.5B. Actions was not on original roadmap."},
    {"name": "Dropbox", "facts": "Launched with demo video, 75K signups before code shipped. 700M registered users. Waitlist went from 5K to 75K overnight."},
    {"name": "Quibi", "facts": "Raised $1.75B. Shut down in 6 months. Canonical product failure from narrative-driven decision making."},
    {"name": "Instagram", "facts": "2B users. Hid like counts in 2019. DAU grew from 500M to 700M in two years after the change."},
    {"name": "Discord", "facts": "200M users. Started for gamers, expanded to all communities. Free with Nitro premium. 19M daily active servers."},
    {"name": "Canva", "facts": "150M users. $40B valuation. Democratized design for non-designers. 190 countries."},
    {"name": "Zoom", "facts": "300M daily meeting participants at peak in 2020. Grew 30x in one year. Simplified one painful thing: joining a call."},
    {"name": "HubSpot", "facts": "$2.2B revenue. Pioneered inbound marketing. 200K+ customers. Went from zero to IPO by teaching before selling."},
    {"name": "Miro", "facts": "70M users. $17.5B valuation. Grew explosively during remote work shift by solving one job: real-time visual collaboration."},
    {"name": "Loom", "facts": "Acquired by Atlassian for $975M. 25M users. Solved async video communication before it was a category."},
    {"name": "Calm", "facts": "100M downloads. $2B valuation. Grew from simple sleep sounds to full mental wellness platform one adjacent step at a time."},
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

def generate_content():
    rng = random.SystemRandom()
    mm  = rng.choice(MENTAL_MODELS)
    co  = rng.choice(COMPANIES)

    prompt = f"""{VOICE_PROMPT}

NICHE: Mental models + product thinking + data.

Company: {co['name']}
Facts about {co['name']}: {co['facts']}

Mental model: {mm['model']}
What it means: {mm['what']}

Write a 2-part Threads thread about {co['name']} that illustrates the mental model.
This post is about {co['name']} only. Do NOT use Amazon, Apple, Netflix, or any other company.

Output exactly this format — two sections separated by "---":

PART 1 (hook, 1/2):
- Open with a sharp, specific observation that creates tension. Make the reader need part 2.
- Introduce the mental model idea without naming it yet.
- End with a question or incomplete thought that pulls them to read on.
- Under 280 characters. No numbering label.

---

PART 2 (payoff):
- What {co['name']} actually did. Specific decision or moment.
- Use a real number from the facts above. Let it land.
- Name the mental model here.
- One line the reader can apply this week.
- Under 320 characters. No numbering label.

No filler. No motivation. No dashes anywhere. No emojis.
Output only the two post texts separated by ---, nothing else."""

    raw = _gemini(prompt, temperature=0.9)

    parts = [p.strip() for p in raw.split("---") if p.strip()]
    if len(parts) >= 2:
        part1, part2 = parts[0], parts[1]
    else:
        # fallback: split roughly in half
        lines = raw.strip().splitlines()
        mid = len(lines) // 2
        part1 = "\n".join(lines[:mid]).strip()
        part2 = "\n".join(lines[mid:]).strip()

    return part1, part2, mm["model"], co["name"]


# ── Threads ───────────────────────────────────────────────────────────────────

def _threads_post(url, data):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_to_threads(part1, part2):
    # Publish root post
    container = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads", {
        "media_type": "TEXT",
        "text": part1,
        "access_token": THREADS_TOKEN,
    })
    time.sleep(2)
    root = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": container["id"],
        "access_token": THREADS_TOKEN,
    })
    root_id = root["id"]

    time.sleep(3)

    # Publish reply (2/2) chained to root
    reply_container = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads", {
        "media_type": "TEXT",
        "text": part2,
        "reply_to_id": root_id,
        "access_token": THREADS_TOKEN,
    })
    time.sleep(2)
    _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": reply_container["id"],
        "access_token": THREADS_TOKEN,
    })

    return root_id


# ── Handler ───────────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        auth = self.headers.get("authorization", "")
        if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
            self._respond(401, {"error": "Unauthorized"})
            return

        try:
            part1, part2, model_name, company_name = generate_content()
            thread_id = post_to_threads(part1, part2)

            self._respond(200, {
                "ok": True,
                "model": model_name,
                "company": company_name,
                "thread_id": thread_id,
                "part1": part1,
                "part2": part2,
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
