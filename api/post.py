"""
Vercel serverless function — generates and posts to Threads.
Triggered 3x/day by GitHub Actions at 7:30 AM, 12:30 PM, 6:30 PM PST.
Strategy: Mental Model + Real Company Story + Data. One week test.
"""

import os
import json
import time
import re
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
# Each entry: model name, what it is, company that used it, what they did, outcome/data

MENTAL_MODELS = [
    {
        "model": "First Principles Thinking",
        "what": "Break every assumption down to its most basic truth, then rebuild from scratch. Ignore what everyone else does.",
        "company": "SpaceX",
        "story": "Everyone said rockets cost $65M because that's what they always cost. Musk asked what the raw materials actually cost. Carbon fiber, aluminum, titanium, copper: $2M. SpaceX built their own instead of buying. Same rocket, 10x cheaper.",
        "data": "SpaceX reduced launch costs from $65M to $6M per launch. Falcon 9 now holds 60% of the global commercial launch market."
    },
    {
        "model": "Pareto Principle",
        "what": "80% of your results come from 20% of your causes. Find those 20% and go all in.",
        "company": "Microsoft",
        "story": "Microsoft's engineers analyzed Windows crash reports and found that 20% of bugs caused 80% of all crashes and freezes. They stopped spreading fixes evenly and prioritized those bugs exclusively. Stability improved more in one release than the three before it.",
        "data": "Fixing the top 20% of reported bugs eliminated 80% of Windows errors in production."
    },
    {
        "model": "Inversion Thinking",
        "what": "Don't ask how to succeed. Ask what would guarantee failure and systematically avoid it.",
        "company": "Apple",
        "story": "Apple's design process doesn't start with 'how do we make a great phone'. It starts with a list of everything that makes phones miserable: bad battery, cluttered interface, ugly hardware. They eliminate those first. What's left is the product.",
        "data": "iPhone has held over 55% US smartphone market share for 10 consecutive years."
    },
    {
        "model": "Systems Thinking",
        "what": "Every action has ripple effects. Optimizing one part of a system often breaks another. See the whole before you touch the parts.",
        "company": "Toyota",
        "story": "Toyota's rivals optimized each factory station individually. Toyota mapped the entire value stream from raw steel to delivered car. They found that parts spent 95% of their time waiting, not being worked on. They fixed the wait, not the stations.",
        "data": "Toyota produces a car every 57 seconds. Its inventory turnover is 15x the US auto industry average."
    },
    {
        "model": "Second-Level Thinking",
        "what": "First-level thinking asks what happens next. Second-level thinking asks what happens after that.",
        "company": "Instagram",
        "story": "Instagram removed public likes in 2019. First-level effect: less vanity metrics. Second-level effect: creators stopped obsessing over performance and started posting more authentically. Engagement rates went up. Time on app increased.",
        "data": "Instagram's daily active users grew from 500M to 700M in the two years after the change."
    },
    {
        "model": "Circle of Competence",
        "what": "Know what you know well. Know the edges of that circle. Never pretend the circle is bigger than it is.",
        "company": "Berkshire Hathaway",
        "story": "Warren Buffett passed on every major tech company in the 90s dot-com boom. He admitted he didn't understand how to value them. While others lost 80% of their portfolios, Berkshire returned 9% annually through the crash.",
        "data": "Buffett's 60-year average annual return is 19.8%. The S&P 500 averaged 10.2% over the same period."
    },
    {
        "model": "Occam's Razor",
        "what": "Given two explanations, the simpler one is usually right. Given two solutions, the simpler one usually wins.",
        "company": "Google",
        "story": "In 1998, every search engine homepage was a portal: news, weather, stocks, ads, links. Google launched with a white page and a search box. Users didn't need to be trained. The simplest interface won the entire market.",
        "data": "Google now processes 8.5 billion searches per day. Yahoo, the leader in 1998, sold to Verizon for $4.5B in 2017."
    },
    {
        "model": "Compound Interest",
        "what": "Small consistent improvements compound into results that feel impossible. The math only works if you don't stop.",
        "company": "Amazon Prime",
        "story": "Amazon launched Prime in 2005 as a $79/year bet. Each year they added one small benefit: free movies, then music, then grocery delivery. No single addition looked like much. After 15 compounding years it had become the main reason people shopped on Amazon at all.",
        "data": "Prime has 200 million members globally. Prime members spend $1,400/year vs. $600 for non-members."
    },
    {
        "model": "Probabilistic Thinking",
        "what": "Don't predict one outcome. Model a range of outcomes and their likelihoods. Decisions should match the distribution, not the prediction.",
        "company": "Netflix",
        "story": "Netflix doesn't greenlight shows by predicting which will be hits. They model the probability distribution across 100 shows. Their goal is a portfolio that returns well on average, not a single bet that might be right. House of Cards was a probabilistic bet, not a certainty.",
        "data": "Netflix original content budget reached $17B in 2023. Their hit rate is 3x higher than traditional studios."
    },
    {
        "model": "Redundancy",
        "what": "Build backup systems before you need them. The cost of redundancy is always less than the cost of failure.",
        "company": "AWS",
        "story": "AWS designed every data center assuming the one next to it would fail. They built Availability Zones so that no single outage could take down a customer's application. Most of their competitors built one big data center and called it reliable.",
        "data": "AWS has 99.99% uptime SLA across its core services. A 0.01% outage at AWS affects more systems than most countries' entire internet infrastructure."
    },
    {
        "model": "Working Backwards",
        "what": "Write the press release before writing any code. Forces clarity on who benefits and why.",
        "company": "Amazon",
        "story": "Every feature starts with a fake press release. The team that skipped it built the Fire Phone. The teams that didn't built Prime and AWS.",
        "data": "AWS grew to $90B revenue. Fire Phone was discontinued in 12 months."
    },
    {
        "model": "Jobs To Be Done",
        "what": "People don't buy products. They hire them to do a job. The job doesn't change. The product does.",
        "company": "Intercom",
        "story": "Intercom mapped why people actually used their chat tool. The job wasn't 'chat'. It was 'close a deal before the prospect leaves the page'. That insight reshaped their entire product.",
        "data": "Intercom grew to $150M ARR before pivoting to AI-first."
    },
    {
        "model": "Chaos Engineering",
        "what": "Intentionally break your system in production to find weaknesses before they find you.",
        "company": "Netflix",
        "story": "Netflix built Chaos Monkey, a tool that randomly kills production servers. Their engineers had to build systems resilient enough to survive it. Most companies only find these failures when customers do.",
        "data": "Netflix achieves 99.99% uptime serving 260 million subscribers globally."
    },
    {
        "model": "Minimum Viable Product",
        "what": "The smallest thing you can build that tests your most important assumption.",
        "company": "Dropbox",
        "story": "Drew Houston didn't build Dropbox first. He made a 3-minute demo video showing how it would work. 75,000 people signed up overnight. Then he built it.",
        "data": "The waitlist went from 5,000 to 75,000 in one day. Zero code shipped."
    },
    {
        "model": "North Star Metric",
        "what": "One number that captures the core value you deliver to users. Everything else is secondary.",
        "company": "Airbnb",
        "story": "Airbnb's north star was nights booked, not revenue, not signups. Every team's work was measured against that single metric. It aligned 6,000 people without a memo.",
        "data": "Airbnb went from near-bankruptcy in 2009 to 100 million nights booked annually."
    },
    {
        "model": "Flywheel Effect",
        "what": "A self-reinforcing loop where each part makes the next part easier. Hard to start. Impossible to stop.",
        "company": "Amazon",
        "story": "More sellers attract more buyers. More buyers attract more sellers. Lower prices attract both. This is why Amazon Marketplace works. No single team drives it. The loop drives itself.",
        "data": "Third-party sellers now account for 60% of Amazon's total sales volume."
    },
    {
        "model": "Pre-mortem",
        "what": "Before launching, assume the project failed. Work backwards to find out why.",
        "company": "Google Ventures",
        "story": "GV runs pre-mortems before every major investment. The team imagines it's 12 months later and the startup failed. They list every possible reason. Half those reasons get fixed before launch.",
        "data": "GV's portfolio includes Uber, Slack, and 23andMe. Pre-mortems are mandatory."
    },
    {
        "model": "Loss Aversion",
        "what": "People feel losses twice as strongly as equivalent gains. Design for what users might lose, not just gain.",
        "company": "Duolingo",
        "story": "Duolingo's streak feature works because losing a 30-day streak hurts more than gaining a 30-day streak feels good. They designed the anxiety on purpose. It's not gamification. It's loss aversion.",
        "data": "Duolingo has 500 million users. Streak users retain at 2x the rate of non-streak users."
    },
    {
        "model": "Anchoring",
        "what": "The first number someone sees shapes every decision that follows.",
        "company": "Apple",
        "story": "Steve Jobs revealed the iPad at $999 on screen, held it, then said 'We're pricing it at $499.' Every person in the room felt they were getting a deal. The anchor was fake. The feeling was real.",
        "data": "iPad sold 300,000 units on day one. The anchoring technique is now standard in product launches."
    },
    {
        "model": "Scarcity Principle",
        "what": "People want what they can't easily have. Artificial scarcity drives urgency.",
        "company": "Gmail",
        "story": "Gmail launched in 2004 as invite-only. You needed to know someone who had an account. Invites sold on eBay for $150. Google created scarcity intentionally to drive demand for a free product.",
        "data": "Gmail reached 1 million users 1 year after invite-only launch. It now has 1.8 billion users."
    },
    {
        "model": "Dogfooding",
        "what": "Use your own product before shipping it to customers.",
        "company": "Slack",
        "story": "Slack was built internally at a gaming company called Tiny Speck. The team used it every day while building their actual product. When the game failed, they had accidentally built something people couldn't stop using. They shipped the tool, not the game.",
        "data": "Slack grew to $7B ARR and was acquired by Salesforce for $27.7B in 2021."
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
    """Cycle through mental models so we never repeat within a week."""
    idx = post_number % len(MENTAL_MODELS)
    return MENTAL_MODELS[idx]


def get_post_number():
    """Unique index per 8-hour slot across the year. Never repeats the same model twice in a row."""
    now = datetime.now(timezone.utc)
    day_of_year = now.timetuple().tm_yday
    hour = now.hour
    # Slot 0 = 7:30 AM PST (15:30 UTC), Slot 1 = 12:30 PM PST (20:30 UTC), Slot 2 = 6:30 PM PST (02:30 UTC next day)
    slot = 0 if hour < 19 else (1 if hour < 23 else 2)
    return (day_of_year - 1) * 3 + slot


def refine_draft(draft):
    prompt = f"""You are a Threads engagement editor. Make this post land harder.

Original post:
\"\"\"{draft}\"\"\"

Rules:
- Rewrite the opening line to stop the scroll. Create tension or curiosity immediately.
- Tighten every line. Remove anything that doesn't earn its place.
- Keep the mental model name, the company name, and the outcome data. These are non-negotiable.
- Keep the core insight intact.
- Stay under 400 characters total.
- No emojis, no hashtags, no LinkedIn tone.
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

Today's mental model to write about:
Model: {mm['model']}
What it is: {mm['what']}
Company: {mm['company']}
What they did: {mm['story']}
Data/outcome: {mm['data']}

{f"Recent AI/tech news for additional context (optional, use only if relevant):{chr(10)}{headlines_str}" if headlines_str else ""}

Write a single Threads post using this structure:
1. Open with a sharp, specific observation about the mental model or the company story. First line must stop the scroll.
2. Explain what the company actually did. Be specific. Name the product or decision.
3. End with the outcome or data. Let the number land.
4. Optional: one-line insight the reader can take away.

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
