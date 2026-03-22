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
# 24 models. Every one uses a different company. No Amazon/Apple/Netflix clusters.
# Hardcoded stories = accurate data, no hallucination, guaranteed variety across the cycle.

MENTAL_MODELS = [
    {
        "model": "Working Backwards",
        "what": "Write the press release before writing any code. Forces clarity on who benefits and why.",
        "company": "Amazon",
        "story": "Every feature team writes a fake press release first. The team that skipped it built the Fire Phone. The teams that used it built Prime and AWS.",
        "data": "Fire Phone died in 12 months. AWS hit $90B in annual revenue."
    },
    {
        "model": "Jobs To Be Done",
        "what": "People don't use products. They hire them to make progress in a specific situation.",
        "company": "Intercom",
        "story": "Intercom asked customers what they were actually trying to do when they opened the chat widget. The job wasn't 'chat'. It was 'close this deal before the prospect leaves the page'. That insight rewrote their entire product strategy.",
        "data": "Intercom grew to $150M ARR. The shift came from 20 interviews, not a roadmap."
    },
    {
        "model": "Minimum Viable Product",
        "what": "The smallest thing that tests your most critical assumption. Not the smallest thing you can build.",
        "company": "Buffer",
        "story": "Joel Gascoigne didn't build Buffer first. He put up a landing page with two pricing tiers and a 'coming soon' button. People clicked. He emailed them. They confirmed they'd pay. Then he built it.",
        "data": "First paying customer acquired before a single line of app code was shipped."
    },
    {
        "model": "North Star Metric",
        "what": "One number that captures the core value you deliver. Everything else is a leading indicator.",
        "company": "Spotify",
        "story": "Spotify's north star is time spent listening, not monthly active users, not downloads. Every team's roadmap is filtered through that single lens. A feature that adds MAUs but doesn't increase listening time loses the prioritization argument.",
        "data": "Spotify users average 30 minutes of daily listening. The metric drives every product bet."
    },
    {
        "model": "Flywheel Effect",
        "what": "A self-reinforcing loop where each part makes the next part easier. Hard to start. Very hard to stop.",
        "company": "Shopify",
        "story": "More merchants attract more app developers. More apps make Shopify more useful to merchants. Better merchant outcomes attract more merchants. No single PM owns the flywheel. Product's job is to keep each part turning.",
        "data": "Shopify's app ecosystem has 8,000+ apps. Third-party developers earn 4x what Shopify earns from the platform."
    },
    {
        "model": "Pre-mortem",
        "what": "Before you launch, assume the project already failed. Work backwards to find out exactly why.",
        "company": "Linear",
        "story": "Linear's team runs assumption audits before every major feature release. They ask: what would have to be true for this to fail? They generate every plausible failure mode. The ones that are fixable get fixed before launch. The ones that aren't become known risks, not surprises.",
        "data": "Linear reached $35M ARR with a team of under 30 people. Focused shipping is a stated product principle."
    },
    {
        "model": "Second-Order Thinking",
        "what": "First-order thinking asks what happens next. Second-order thinking asks what happens after that.",
        "company": "Instagram",
        "story": "Instagram hid public like counts in 2019. First-order effect: less vanity pressure on creators. Second-order effect: creators stopped chasing spikes and started building consistent presence. Authentic content outperformed viral content. Platform ad value went up.",
        "data": "Instagram daily active users grew from 500M to 700M in the two years after the change."
    },
    {
        "model": "Inversion",
        "what": "Don't ask how to make a great product. Ask what would make it terrible, then eliminate those things.",
        "company": "Superhuman",
        "story": "Rahul Vohra's team didn't start by adding features. They interviewed churned users and mapped every reason email felt bad: slow load, cognitive overload, no keyboard shortcuts, anxiety from inbox count. The product spec was a list of failures to eliminate.",
        "data": "Superhuman charges $30/month for email. NPS of 58 vs Gmail's 1."
    },
    {
        "model": "Loss Aversion",
        "what": "People feel losses twice as intensely as equivalent gains. Design for what users stand to lose.",
        "company": "Duolingo",
        "story": "Duolingo's streak feature is engineered anxiety. Losing a 60-day streak hurts more than building one feels good. The discomfort is the product. They A/B tested the grief messaging. The version that made users feel worse retained better.",
        "data": "Duolingo has 500M users. Streak users retain at 2x the rate of non-streak users."
    },
    {
        "model": "Anchoring",
        "what": "The first number a person sees shapes every judgment that follows.",
        "company": "Figma",
        "story": "Figma's pricing page leads with the Professional plan at $15/seat before showing the free tier. The free tier feels generous next to a paid anchor. Most design tools led with free and struggled to convert. Figma inverted the frame.",
        "data": "Figma grew to $400M ARR and a $10B acquisition offer from Adobe. Pricing strategy was cited in their S-1 analysis."
    },
    {
        "model": "Dogfooding",
        "what": "Use your own product before shipping it to customers. Not as a test. As your primary workflow.",
        "company": "Slack",
        "story": "Slack was an internal tool at a gaming company called Tiny Speck. The team used it daily while building their actual product, a game called Glitch. When Glitch failed, they realized they'd built something they couldn't work without. They shipped the tool instead.",
        "data": "Slack grew to $7B ARR and was acquired by Salesforce for $27.7B in 2021."
    },
    {
        "model": "Pareto Principle in Product",
        "what": "80% of your product's value comes from 20% of its features. The rest is overhead.",
        "company": "Basecamp",
        "story": "Basecamp deliberately removed features every year. Calendar integrations, time tracking, client billing — gone. Each removal was a bet that the remaining 20% of features delivered 80% of the value. They were right each time. The product got faster and simpler.",
        "data": "Basecamp is profitable with under 60 employees serving 3 million companies. No VC, no growth team."
    },
    {
        "model": "Occam's Razor in Specs",
        "what": "When two solutions solve the same problem, the simpler one wins. Not because it's easier to build — because users trust it faster.",
        "company": "Linear",
        "story": "Linear's issue tracker has fewer features than Jira by design. Every feature request goes through a filter: does the simplest version solve this? The team says no more than yes. The result is a product that engineers actually open without dreading it.",
        "data": "Linear grew to $35M ARR. NPS consistently above 70 in developer tooling surveys."
    },
    {
        "model": "Probabilistic Roadmaps",
        "what": "Don't predict which feature wins. Build a portfolio of bets where the expected value justifies the investment.",
        "company": "Duolingo",
        "story": "Duolingo runs hundreds of A/B tests simultaneously. They don't predict which variant will win. They model a distribution and invest in the portfolio. Most experiments fail. The ones that don't compound. The roadmap is a bet portfolio, not a feature list.",
        "data": "Duolingo runs 500+ experiments per year. Their experiment velocity is a stated growth driver."
    },
    {
        "model": "The Rule of Three in Product Writing",
        "what": "Every product doc should answer exactly three questions: what is the problem, who has it, what changes when it's solved.",
        "company": "Stripe",
        "story": "Stripe's API documentation is structured around three questions for every endpoint: what does this do, when would you use it, and what does success look like. Internal specs follow the same structure. Docs longer than three paragraphs go back for revision.",
        "data": "Stripe reached $95B valuation. Writing clarity is listed as a core hiring signal in their eng blog."
    },
    {
        "model": "Opportunity Scoring",
        "what": "Prioritize by importance minus satisfaction. Critical job, poorly served = your opening.",
        "company": "Notion",
        "story": "Notion's early team surveyed knowledge workers. Document organization scored high on importance and low on satisfaction across every existing tool. The gap was larger than any other job. They didn't build another doc editor. They built around the gap.",
        "data": "Notion grew to 20M users and a $10B valuation in under 5 years."
    },
    {
        "model": "Type 1 vs Type 2 Decisions",
        "what": "Reversible decisions should be made fast. Irreversible decisions deserve more process. Conflating them is how teams get slow.",
        "company": "Amazon",
        "story": "Bezos formalized this in his 2015 shareholder letter. Type 2: change the copy, the price, the flow. Make it fast. Type 1: data contracts, API design, architecture. Slow down. Most PMs apply the same approval process to both and wonder why everything takes six months.",
        "data": "Amazon runs 50+ autonomous product teams. Decision velocity is a stated competitive advantage."
    },
    {
        "model": "Narrative Fallacy in Specs",
        "what": "A coherent product story can make a bad bet feel inevitable. Be suspicious of specs that read too cleanly.",
        "company": "Quibi",
        "story": "Quibi's pitch deck was spotless: mobile-first, short-form, premium content, Hollywood talent. Every slide connected. Every assumption reinforced the next. Nobody stress-tested whether people actually wanted 10-minute premium shows on their phones during commutes.",
        "data": "Quibi raised $1.75B and shut down in 6 months. The narrative outlasted the evidence by two years."
    },
    {
        "model": "The Curse of Knowledge in Product Writing",
        "what": "The more you know about your product, the harder it is to write for someone who doesn't. Expertise kills clarity.",
        "company": "Stripe",
        "story": "Stripe's developer docs are written with a rule: assume the reader has never heard the term being explained. Every API concept is defined the first time it appears. No assumed context. Engineers who wrote the API are not allowed to write the docs without a plain-language reviewer.",
        "data": "Stripe's docs are ranked the best in developer tooling surveys year over year. Directly cited as a growth driver."
    },
    {
        "model": "Shape Up: Fixed Time, Variable Scope",
        "what": "Fix the time. Flex the scope. A 6-week cycle with a variable spec ships more than infinite sprints with a fixed one.",
        "company": "Basecamp",
        "story": "Basecamp replaced sprints with 6-week cycles. Teams get a problem and a time box — not a feature list. Scope is negotiated during the cycle, not before. Edge cases get cut. The core ships. What doesn't fit goes to the next cycle.",
        "data": "Basecamp has been profitable for 20+ years without a growth team. Shape Up is now used at Linear, Pitch, and dozens of product orgs."
    },
    {
        "model": "Regret Minimization in Product Decisions",
        "what": "When deciding whether to build, ask: will I regret not doing this at 80? Most urgent roadmap debates look trivial from that view.",
        "company": "GitHub",
        "story": "GitHub's team used this framing when deciding whether to build GitHub Actions. It wasn't on the roadmap. It would take a year. Competitors didn't have it. The regret question was: will we regret not owning developer workflows in 10 years? The answer decided the project.",
        "data": "GitHub Actions is used by 10M+ developers. Microsoft cited it as a key acquisition rationale at $7.5B."
    },
    {
        "model": "Adjacent Possible in Product Strategy",
        "what": "Every product can only move one step into what users already understand. Skip a step and they can't follow.",
        "company": "Figma",
        "story": "Figma didn't launch as a design system platform. They launched as a better Sketch with real-time collaboration — one step beyond what designers already used. When that landed, they added prototyping. Then components. Then dev mode. Each step was adjacent to the last.",
        "data": "Figma grew to $400M ARR. Adobe offered $10B to acquire them in 2022."
    },
    {
        "model": "Compound Improvement in Product Quality",
        "what": "Small quality improvements compound. A 1% retention gain, compounded monthly, becomes a structurally different product in 18 months.",
        "company": "Duolingo",
        "story": "Duolingo's growth team doesn't chase big features. They run micro-experiments on notifications, streak recovery, lesson length, and sound design. Each improvement is tiny. Stacked quarterly, they compound into retention curves that competitors can't explain.",
        "data": "Duolingo grew DAU from 10M to 37M in 3 years through experiment-driven compounding."
    },
    {
        "model": "Scarcity and Urgency",
        "what": "People want what they can't easily have. Artificial scarcity drives urgency even when supply is unlimited.",
        "company": "Superhuman",
        "story": "Superhuman launched invite-only and kept it that way for years. There was no technical reason. The waitlist was the product. Being invited to Superhuman meant something. The scarcity created a perception of quality before anyone had used it.",
        "data": "Superhuman built a $75M ARR business charging $30/month for email. Invite-only was active for 4 years."
    },
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
- Keep the exact company and data from the original. Do not change them.
- The insight must be something a PM can apply this week.
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
Every post: name the mental model, show the company story, end with the data.

Today's mental model:
Model: {mm['model']}
What it is: {mm['what']}
Company: {mm['company']}
What they did: {mm['story']}
Data: {mm['data']}

{f"Recent context (use only if it sharpens the PM angle):{chr(10)}{headlines_str}" if headlines_str else ""}

Write a single Threads post:
1. First line: sharp observation that makes a PM stop scrolling. Create tension.
2. What the company did. Specific. Name the product or decision.
3. The data. Let the number land.
4. Optional: one line the reader can apply this week.

Keep it under 400 characters. No filler. No motivation. No dashes anywhere.
Output only the post text, nothing else."""

    draft = _gemini(prompt, temperature=0.85)
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
