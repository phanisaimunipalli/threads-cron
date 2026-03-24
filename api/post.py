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


# ── Company Pool ──────────────────────────────────────────────────────────────
# Mass-recognition companies only. Each entry has a counterintuitive tension
# baked in — a specific moment or decision that surprises people.

COMPANIES = [
    {"name": "Zoom", "tension": "Most people think Zoom won because of video quality. It won because joining a call required zero friction. Every competitor made you download something first.", "data": "300M daily participants at peak. Grew 30x in one year. Eric Yuan's original pitch was rejected by Cisco, WebEx's parent."},
    {"name": "Slack", "tension": "Slack was not built as a product. It was a failed game studio's internal tool. They shipped the accident, not the game.", "data": "$7B ARR. Acquired for $27.7B. The game (Glitch) had 0 users at shutdown. Slack had thousands."},
    {"name": "Instagram", "tension": "Instagram killed the feature everyone used most — public like counts. Creators were furious. Engagement went up.", "data": "DAU grew from 500M to 700M in two years after hiding likes. Ad revenue increased as authentic content outperformed viral."},
    {"name": "Duolingo", "tension": "Duolingo deliberately made users feel anxious about losing their streak. The grief was the product. They A/B tested which notification made people feel worst.", "data": "500M users. Streak users retain at 2x rate. DAU grew from 10M to 37M in 3 years purely through behavioral design."},
    {"name": "Notion", "tension": "Notion launched to almost no one and grew to 20M users with zero paid marketing. They let their own users build the growth engine.", "data": "20M users. $10B valuation. Template gallery — entirely user-generated — is their top acquisition channel."},
    {"name": "Figma", "tension": "Every design tool in 2016 was a desktop app. Figma built in the browser when browsers were considered too slow for design. Everyone said it was technically impossible.", "data": "$400M ARR. Adobe offered $10B to acquire them. The browser bet is why they have real-time multiplayer and Adobe doesn't."},
    {"name": "Airbnb", "tension": "Airbnb was near-bankrupt in 2009 and survived by selling novelty cereal boxes. The founders went door to door photographing listings themselves because they noticed bad photos killed bookings.", "data": "100M nights booked annually. $75B valuation. Professional photography became a product feature, not a marketing budget line."},
    {"name": "Spotify", "tension": "Spotify convinced record labels it was saving the music industry while building a product that made owning music feel pointless.", "data": "600M users. 240M paid subscribers. Average user listens 30 min/day. Artists earn $0.003 per stream — the tension that never resolved."},
    {"name": "Dropbox", "tension": "Dropbox validated a $10B product with a 3-minute video of software that did not exist. The demo was fake. The waitlist was real.", "data": "Waitlist went from 5K to 75K overnight. 700M registered users. Zero code existed when the first customer signed up."},
    {"name": "Uber", "tension": "Uber's surge pricing launched to public outrage. Every PM instinct said remove it. They kept it. Supply went up. Wait times went down.", "data": "Surge pricing increased driver supply by 70-80% during peak demand. Uber operates in 70 countries. $31B revenue in 2023."},
    {"name": "Twitter", "tension": "Twitter's 140-character limit was a technical constraint from SMS, not a product decision. The constraint became the product's identity.", "data": "350M users built their communication style around an arbitrary SMS limitation. The constraint drove more engagement than any feature they intentionally designed."},
    {"name": "YouTube", "tension": "YouTube's recommendation algorithm optimized for watch time, not satisfaction. Users watched more and reported feeling worse. The metric won anyway.", "data": "2.7B monthly users. 500 hours of video uploaded per minute. Watch time optimization drove 70% of all views through recommendations."},
    {"name": "WhatsApp", "tension": "WhatsApp had 5 engineers and 450M users when Facebook acquired it. They grew that large by doing almost nothing — no ads, no growth team, no analytics.", "data": "Acquired for $19B in 2014. Now 2B users. The team that built it was smaller than most companies' marketing departments."},
    {"name": "TikTok", "tension": "TikTok's most powerful product decision was showing your content to strangers first, not your followers. Every other platform built around your social graph. TikTok ignored it.", "data": "1B+ users in 3 years. Average session 95 minutes/day. The For You page serves content before you follow anyone — zero friction to value."},
    {"name": "Canva", "tension": "Every designer told Canva it was a toy for non-designers. That was exactly the point. They built for the person Photoshop ignored.", "data": "150M users. $40B valuation. 190 countries. Professional designers are a minority of their user base by design."},
    {"name": "Shopify", "tension": "Shopify's biggest product bet was making it easier to compete with Amazon rather than partnering with it. They bet on independent commerce when everyone else was listing on marketplaces.", "data": "4M merchants. $7B annual revenue. Third-party app developers earn 4x what Shopify earns from the ecosystem."},
    {"name": "GitHub", "tension": "Microsoft acquired GitHub for $7.5B and did almost nothing with it for two years. The product that eventually came — GitHub Actions — was not on the roadmap at acquisition.", "data": "100M developers. GitHub Actions used by 10M+. The best product decision post-acquisition was one they didn't plan."},
    {"name": "Superhuman", "tension": "Superhuman charges $30/month for email and was invite-only for 4 years. The waitlist was the product. Scarcity created the perception of quality.", "data": "NPS of 58 vs Gmail's 1. $75M ARR. The invite wall had no technical reason — it was a positioning decision."},
    {"name": "Stripe", "tension": "Stripe launched in 2010 when PayPal had already won payments. They won anyway by solving for developers instead of businesses.", "data": "$95B valuation. Powers 0.5% of global GDP in transactions. The API documentation is cited as a growth driver more than any sales motion."},
    {"name": "Linear", "tension": "Linear entered a market dominated by Jira — a product 95% of engineers hate but every company uses. They won by making engineers actually want to open it.", "data": "$35M ARR. Team under 50. NPS above 70. The product has fewer features than Jira by design — every feature request is filtered through subtraction first."},
    {"name": "Basecamp", "tension": "Basecamp removed features every year and got more profitable each time. In an industry that measures growth by adding, they grew by subtracting.", "data": "Profitable 20+ years. Under 60 employees. 3M companies. No VC funding ever taken. Shape Up methodology now used by teams at Linear, Pitch, and dozens of others."},
    {"name": "Intercom", "tension": "Intercom's customers thought they were buying chat software. Intercom realized the job was closing a deal before the prospect left the page. The insight rewrote their entire roadmap.", "data": "$150M ARR. The pivot came from 20 customer interviews, not a data dashboard."},
    {"name": "Snapchat", "tension": "Snapchat's disappearing messages were considered a privacy gimmick. The real product insight was that ephemerality made people post more honestly, not less.", "data": "375M daily users. Stories feature was copied by Instagram, WhatsApp, YouTube, and LinkedIn within 18 months — the clearest signal a product idea has won."},
    {"name": "Pinterest", "tension": "Pinterest looked like a mood board app for recipes. It was actually a purchase intent engine. Users saved products they planned to buy, not just admire.", "data": "465M monthly users. Pinners are 7x more likely to purchase than non-pinners. $3B revenue driven almost entirely by shopping intent disguised as inspiration."},
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

def get_recent_companies(n=2):
    """Fetch last n root posts and return company names found in them."""
    try:
        url = f"{THREADS_API}/{THREADS_USER_ID}/threads?fields=text&limit=10&access_token={THREADS_TOKEN}"
        req = urllib.request.urlopen(url, timeout=8)
        posts = json.loads(req.read()).get("data", [])
        used = set()
        checked = 0
        for post in posts:
            text = post.get("text", "").lower()
            for co in COMPANIES:
                if co["name"].lower() in text:
                    used.add(co["name"])
                    break
            else:
                continue
            checked += 1
            if checked >= n:
                break
        return used
    except Exception:
        return set()


def generate_content():
    rng = random.SystemRandom()
    mm  = rng.choice(MENTAL_MODELS)

    recent = get_recent_companies(n=2)
    pool   = [c for c in COMPANIES if c["name"] not in recent] or COMPANIES
    co     = rng.choice(pool)

    prompt = f"""{VOICE_PROMPT}

NICHE: Mental models + product thinking + data.

Company: {co['name']}
The counterintuitive tension: {co['tension']}
Real data: {co['data']}

Mental model: {mm['model']}
What it means: {mm['what']}

Write a 2-part Threads thread using the tension above as your hook.
This post is about {co['name']} only.

Output exactly two sections separated by "---":

PART 1 (hook):
- Open with the counterintuitive tension. Lead with what most people believe is wrong.
- Use this pattern: "Most people think [X]. They're wrong." or "Everyone said [X]. [Company] did the opposite."
- Do NOT name the mental model yet. Build the curiosity.
- End with a cliffhanger or question that makes the reader need part 2.
- Under 240 characters.

---

PART 2 (payoff):
- Reveal what {co['name']} actually did and why it worked.
- Use a specific number from the data above. Let it land on its own line.
- Name the mental model naturally — don't force it as a label.
- Last line: one thing the reader can apply this week.
- Under 320 characters.

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


PART3 = "I post one mental model + product story every evening.\nFollow if that's useful."


# ── Threads ───────────────────────────────────────────────────────────────────

def _threads_post(url, data):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _create_and_publish(text, reply_to_id=None):
    payload = {
        "media_type": "TEXT",
        "text": text,
        "access_token": THREADS_TOKEN,
    }
    if reply_to_id:
        payload["reply_to_id"] = reply_to_id
    container = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads", payload)
    time.sleep(2)
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": container["id"],
        "access_token": THREADS_TOKEN,
    })
    return result["id"]


def post_to_threads(part1, part2):
    root_id  = _create_and_publish(part1)
    time.sleep(3)
    reply_id = _create_and_publish(part2, reply_to_id=root_id)
    time.sleep(3)
    _create_and_publish(PART3, reply_to_id=reply_id)
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
