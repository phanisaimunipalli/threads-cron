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
# Niche: mental models applied to product management and product writing.
# Each entry: model name, what it is, product context story, outcome/data

MENTAL_MODELS = [
    {
        "model": "Working Backwards",
        "what": "Write the press release before writing any code. Forces clarity on who benefits and why before a single decision is locked in.",
        "company": "Amazon",
        "story": "Every Amazon feature starts with a fake press release and FAQ written from the customer's perspective. The team that skipped it built the Fire Phone. The teams that used it built Prime and AWS. The document forces the question: who exactly is this for and why do they care?",
        "data": "AWS grew to $90B in revenue. Fire Phone was discontinued in 12 months."
    },
    {
        "model": "Jobs To Be Done",
        "what": "People don't use products. They hire them to make progress in a specific situation. The job doesn't change. The product does.",
        "company": "Intercom",
        "story": "Intercom's early team interviewed customers and asked what they were trying to accomplish when they opened the chat widget. The job wasn't 'chat'. It was 'close this deal before the prospect leaves the page'. That one insight rewrote their entire product strategy and pricing.",
        "data": "Intercom grew to $150M ARR. The insight came from 20 customer interviews, not a roadmap."
    },
    {
        "model": "Minimum Viable Product",
        "what": "The smallest thing you can ship that tests your most critical assumption. Not the smallest thing you can build.",
        "company": "Dropbox",
        "story": "Drew Houston's most important assumption was that people wanted frictionless file sync badly enough to sign up. He didn't build Dropbox to test it. He filmed a 3-minute demo of software that didn't exist yet. The video tested the assumption. The code came after.",
        "data": "Waitlist went from 5,000 to 75,000 overnight. Zero code shipped."
    },
    {
        "model": "North Star Metric",
        "what": "One number that represents the core value you deliver to users. Everything else is a leading indicator or a distraction.",
        "company": "Airbnb",
        "story": "Airbnb's north star was nights booked, not revenue, not new listings, not signups. Every team mapped their work to that single metric. When two product bets competed for resources, the one that moved nights booked won. It aligned 6,000 people without a memo.",
        "data": "Airbnb went from near-bankruptcy in 2009 to 100 million nights booked annually."
    },
    {
        "model": "Flywheel Effect",
        "what": "A self-reinforcing loop where each part of the system makes the next part easier. Hard to start. Very hard to stop.",
        "company": "Amazon Marketplace",
        "story": "More sellers bring more selection. More selection attracts more buyers. More buyers make it worth selling. Lower prices attract both. No single PM owns the flywheel. The job of product is to keep each part of the loop turning, not to pick which part matters most.",
        "data": "Third-party sellers account for 60% of Amazon's total sales volume today."
    },
    {
        "model": "Pre-mortem",
        "what": "Before you launch, assume the project already failed. Work backwards to find out exactly why.",
        "company": "Google Ventures",
        "story": "GV runs pre-mortems before every major portfolio decision. The team imagines it's 12 months later and the bet failed. They generate every plausible reason. The exercise surfaces assumptions the team was too close to question. About half the risks found get fixed before launch.",
        "data": "GV's portfolio includes Uber, Slack, and 23andMe. Pre-mortems are part of every sprint."
    },
    {
        "model": "Second-Order Thinking",
        "what": "First-order thinking asks what happens next. Second-order thinking asks what happens after that, and who adapts.",
        "company": "Instagram",
        "story": "Instagram hid public like counts in 2019. First-order effect: less vanity pressure. Second-order effect: creators shifted from chasing spikes to building consistent presence. Authentic content outperformed viral content. The platform's ad value went up because dwell time increased.",
        "data": "Instagram daily active users grew from 500M to 700M in the two years after the change."
    },
    {
        "model": "Inversion",
        "what": "Don't ask how to make a great product. Ask what would make this product terrible, then systematically eliminate those things.",
        "company": "Apple iPhone",
        "story": "Apple's early iPhone reviews started with a list of everything that made existing smartphones miserable: styluses, tiny keyboards, confusing menus, bad battery. The product spec wasn't a list of features to add. It was a list of failures to eliminate. What remained became the product.",
        "data": "iPhone has held over 55% US smartphone market share for 10 consecutive years."
    },
    {
        "model": "Scarcity and Urgency",
        "what": "People want what they can't easily have. Perceived scarcity drives urgency even when supply is artificial.",
        "company": "Gmail",
        "story": "Gmail launched in 2004 as invite-only. You needed someone who already had an account to let you in. Invites sold on eBay for $150. Google manufactured scarcity for a free product. The waitlist became the marketing.",
        "data": "Gmail hit 1 million users in its first year. It now has 1.8 billion active users."
    },
    {
        "model": "Loss Aversion",
        "what": "People feel losses roughly twice as intensely as equivalent gains. Design for what users stand to lose, not just what they'll gain.",
        "company": "Duolingo",
        "story": "Duolingo's streak feature is built entirely on loss aversion. Losing a 60-day streak hurts more than building a 60-day streak feels good. The anxiety is the product. They didn't stumble into this. They designed the discomfort on purpose.",
        "data": "Duolingo has 500M users. Streak users retain at 2x the rate of non-streak users."
    },
    {
        "model": "Anchoring",
        "what": "The first number a person sees shapes every judgment that follows. In product, the anchor is almost always set before the price conversation starts.",
        "company": "Apple iPad",
        "story": "Steve Jobs put $999 on screen during the iPad launch, held it for 30 seconds, then said 'We're pricing it at $499.' The room felt like they were getting a deal. The anchor was fake. The cognitive effect was real. Every product launch since has borrowed this structure.",
        "data": "iPad sold 300,000 units on day one. The anchoring format became standard in product launch decks."
    },
    {
        "model": "Dogfooding",
        "what": "Use your own product before shipping it to customers. Not as a test. As your primary workflow.",
        "company": "Slack",
        "story": "Slack was an internal tool at a gaming company called Tiny Speck. The team used it daily while building their actual product, a game called Glitch. When Glitch failed, they realized they'd accidentally built something they couldn't work without. They shipped the tool instead.",
        "data": "Slack grew to $7B ARR and was acquired by Salesforce for $27.7B in 2021."
    },
    {
        "model": "Pareto Principle in Product",
        "what": "80% of the value your product delivers comes from 20% of its features. The rest is maintenance overhead masquerading as product strategy.",
        "company": "Microsoft Windows",
        "story": "Microsoft's team analyzed crash reports and found that 20% of bugs caused 80% of all Windows failures. They stopped spreading engineering capacity evenly across the backlog and attacked only those bugs. One focused release improved stability more than the three before it combined.",
        "data": "Fixing the top 20% of bugs eliminated 80% of production errors."
    },
    {
        "model": "Occam's Razor in Specs",
        "what": "When two product solutions solve the same problem, the simpler one is almost always better. Not because it's easier to build. Because it's easier for users to trust.",
        "company": "Google Search",
        "story": "In 1998, every search engine homepage was a portal: news feeds, weather widgets, stock tickers, display ads, category links. Google launched with a white page and a text box. There was nothing to learn. Users didn't need onboarding. The simplest surface won the entire market.",
        "data": "Google processes 8.5 billion searches per day. Yahoo, the dominant portal in 1998, sold to Verizon for $4.5B in 2017."
    },
    {
        "model": "Probabilistic Roadmaps",
        "what": "Don't predict which feature will win. Model a portfolio of bets where the expected value across all of them justifies the investment.",
        "company": "Netflix Originals",
        "story": "Netflix doesn't greenlight shows by predicting hits. They model probability distributions. The goal is a portfolio that performs well in aggregate, not a single bet that might be right. House of Cards was a probabilistic bet against a distribution, not a conviction call.",
        "data": "Netflix's $17B content budget produces a hit rate 3x higher than traditional studios."
    },
    {
        "model": "Chaos Engineering Applied to Products",
        "what": "Intentionally stress-test your product's assumptions before users find the failure modes for you.",
        "company": "Netflix",
        "story": "Netflix built Chaos Monkey to randomly kill production servers. Engineers had to design systems that survived. The same logic applies to product: run assumption audits before launch. Ask which belief, if wrong, kills the feature. Most teams only discover this after shipping.",
        "data": "Netflix serves 260 million subscribers at 99.99% uptime."
    },
    {
        "model": "The Rule of Three in Product Writing",
        "what": "Every product document should answer three questions and only three: what is the problem, who has it, and what changes for them when it's solved.",
        "company": "Stripe",
        "story": "Stripe's internal product specs are notoriously short. Not because the problems are simple. Because the writers are forced to reduce before they write. A spec that can't be stated in three clean paragraphs usually means the thinking isn't done yet.",
        "data": "Stripe reached $95B valuation with a team that prizes writing clarity as a core product skill."
    },
    {
        "model": "Opportunity Scoring",
        "what": "Prioritize by importance minus satisfaction. If users say a job is critical but no product does it well, that's your opening.",
        "company": "Notion",
        "story": "Notion's team observed that knowledge workers rated document organization as extremely important but gave existing tools (Word, Google Docs, Confluence) low satisfaction scores. The gap was the opportunity. They didn't build another doc editor. They built around the gap.",
        "data": "Notion grew to 20 million users and a $10B valuation in under 5 years."
    },
    {
        "model": "Type 1 vs Type 2 Decisions",
        "what": "Reversible decisions should be made fast and low in the org. Irreversible decisions deserve more time and more people. Conflating them is how teams get slow.",
        "company": "Amazon",
        "story": "Bezos formalized this distinction in his 2015 shareholder letter. Most product decisions are Type 2: you can change the button color, the copy, the price, the flow. You should make those fast. Type 1 decisions are architecture choices, data contracts, API designs. Those deserve a different process.",
        "data": "Amazon operates 50+ product teams with high autonomy. Decision speed is a stated competitive advantage."
    },
    {
        "model": "Narrative Fallacy in Specs",
        "what": "Humans are pattern-completers. A well-written product story can make a bad bet feel inevitable. Be suspicious of specs that read too cleanly.",
        "company": "Google Glass",
        "story": "Google Glass had a compelling product narrative: ambient computing, hands-free access, the future of work. The story was so coherent that it survived years of internal review. The actual user experience was uncomfortable, antisocial, and unclear. The narrative outlasted the evidence.",
        "data": "Google spent $1B+ on Glass before discontinuing the consumer product in 2015."
    },
    {
        "model": "The Curse of Knowledge in Product Writing",
        "what": "The more you know about your product, the harder it is to write about it for someone who doesn't. Expertise is the enemy of clarity.",
        "company": "Basecamp",
        "story": "Basecamp's team writes all product copy as if the reader has never heard of the product. They ban internal jargon from user-facing text entirely. Every feature name, tooltip, and error message goes through a plain-language filter. The assumption is always: the user knows nothing we haven't told them.",
        "data": "Basecamp has served 3 million companies with a team that has never exceeded 60 people."
    },
    {
        "model": "Shape Up: Fixed Time, Variable Scope",
        "what": "Fix the time, flex the scope. A 6-week cycle with a flexible problem statement ships more than an infinite sprint with a fixed spec.",
        "company": "Basecamp",
        "story": "Basecamp replaced sprints with 6-week cycles where scope is intentionally left variable. Teams are given a problem and a time box, not a feature list. What ships is whatever solves the core problem within the cycle. Edge cases and extensions go to the next cycle, not the current one.",
        "data": "Basecamp has been profitable for 20+ years. Shape Up is now used by teams at Linear, Pitch, and dozens of product orgs."
    },
    {
        "model": "Regret Minimization in Product Decisions",
        "what": "When deciding whether to build something, ask: will I regret not doing this when I'm looking back in 10 years?",
        "company": "Amazon",
        "story": "Bezos used this framework before leaving a high-paying finance job to start Amazon. The same logic applies to product bets. It forces you to think in outcomes, not in quarterly metrics. Most feature debates that feel urgent look trivial from a 10-year view.",
        "data": "Amazon started as an online bookstore. The regret minimization bet produced a $1.5T company."
    },
    {
        "model": "Adjacent Possible in Product Strategy",
        "what": "Every product can only move one step into what's adjacent to what users already understand. Skip a step and they can't follow.",
        "company": "Figma",
        "story": "Figma didn't launch as an end-to-end design system platform. They launched as a better Sketch with collaboration. Collaboration was one step beyond what designers already used. When that landed, they added prototyping, then components, then dev mode. Each step was adjacent to the last.",
        "data": "Figma grew to $400M ARR and a $10B acquisition offer from Adobe in 4 years."
    },
    {
        "model": "Compound Improvement in Product Quality",
        "what": "Small quality improvements compound. A 1% better retention rate, compounded monthly, becomes a structurally different product in 18 months.",
        "company": "Amazon Prime",
        "story": "Amazon launched Prime in 2005 as one bet: $79/year for free shipping. Each year they added one adjacent benefit. Free movies. Then music. Then grocery delivery. No single addition looked transformational. After 15 years of compounding, Prime became the main reason people chose Amazon at all.",
        "data": "Prime has 200 million members. Prime members spend $1,400/year vs. $600 for non-members."
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
    prompt = f"""You are a Threads engagement editor. This account's niche is mental models for product managers and product writers. Make this post land harder for that audience.

Original post:
\"\"\"{draft}\"\"\"

Rules:
- Rewrite the opening line so a product manager feels immediately seen or challenged.
- Tighten every line. Remove anything that doesn't earn its place.
- Keep the mental model name, the company name, and the outcome data. These are non-negotiable.
- The post must feel like a product thinking lesson, not a general business insight.
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

NICHE: This account posts about mental models applied to product management and product writing.
Every post must land as a lesson a product manager or product writer can apply to their work.
Not a general business insight. Not a startup inspiration quote. A product thinking lesson.

Today's mental model:
Model: {mm['model']}
What it is: {mm['what']}
Company: {mm['company']}
What they did: {mm['story']}
Data/outcome: {mm['data']}

{f"Recent context (use only if it sharpens the PM angle):{chr(10)}{headlines_str}" if headlines_str else ""}

Write a single Threads post using this structure:
1. First line: a sharp observation that makes a PM or product writer feel seen. Stop the scroll.
2. Explain what the company or team actually did. Name the product or decision. Be specific.
3. End with the outcome or data. Let the number land.
4. Optional: one line the reader can apply to their own work this week.

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
