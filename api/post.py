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
        "model": "Working Backwards",
        "what": "Write the press release before writing any code. Forces clarity on who benefits and why.",
        "company": "Amazon",
        "story": "Every feature starts with a fake press release. The team that skipped it built the Fire Phone. The teams that didn't built Prime and AWS.",
        "data": "AWS grew to $90B revenue. Fire Phone was discontinued in 12 months."
    },
    {
        "model": "Two-Pizza Rule",
        "what": "If two pizzas can't feed the team, it's too big. Small teams ship faster and own more.",
        "company": "Amazon",
        "story": "Bezos broke up large teams into units of 6 to 10. Each team owns one service end to end. No coordination tax.",
        "data": "Amazon deploys code every 11 seconds. Most companies deploy once a week."
    },
    {
        "model": "Regret Minimization Framework",
        "what": "Imagine yourself at 80 looking back. Would you regret not doing this?",
        "company": "Amazon",
        "story": "Bezos used this to quit his hedge fund job in 1994 and start Amazon. He knew at 80 he wouldn't regret trying. He would regret not trying.",
        "data": "Amazon started in a garage. It's now worth over $1.8 trillion."
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
        "model": "Disagree and Commit",
        "what": "Debate hard, decide fast, align completely. You don't have to agree to commit.",
        "company": "Amazon",
        "story": "Bezos openly disagreed with the launch of Amazon Studios but committed fully after the decision was made. He wrote this into the Leadership Principles. Most companies get stuck in silent disagreement disguised as alignment.",
        "data": "Amazon Studios won 63 Emmy Awards. It didn't exist 15 years ago."
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
        "model": "Conway's Law",
        "what": "Your software architecture will mirror your org chart. You build what your teams can communicate.",
        "company": "Amazon",
        "story": "Amazon reorganized into small independent teams before migrating to microservices. The architecture followed the org structure exactly. Teams that stayed monolithic shipped monoliths.",
        "data": "Amazon has over 1,000 microservices in production. Each owned by one two-pizza team."
    },
    {
        "model": "OKRs",
        "what": "Objectives and Key Results. What you want to achieve and how you'll know you got there.",
        "company": "Google",
        "story": "John Doerr brought OKRs from Intel to Google when it had 40 employees. Larry Page was skeptical. They adopted it anyway. Every quarter, every team publishes OKRs publicly inside the company.",
        "data": "Google has used OKRs for 25 years. It now has 180,000 employees."
    },
    {
        "model": "Bikeshedding",
        "what": "Teams spend disproportionate time on trivial decisions and skip the hard ones.",
        "company": "Every company",
        "story": "C. Northcote Parkinson observed that a committee approving a nuclear plant spent 2 minutes on the reactor and 45 minutes debating the color of the bike shed. Most sprint planning meetings are bike sheds.",
        "data": "Studies show 50% of meeting time is spent on topics that affect less than 5% of outcomes."
    },
    {
        "model": "Inversion Thinking",
        "what": "Instead of asking how to succeed, ask what would guarantee failure. Then avoid that.",
        "company": "Charlie Munger and Apple",
        "story": "Apple doesn't ask how to make a great phone. They ask what makes phones terrible: bad battery, ugly design, confusing interface. They eliminate those first. The great product is what's left.",
        "data": "iPhone has held over 55% US smartphone market share for 10 consecutive years."
    },
    {
        "model": "5 Whys",
        "what": "Ask why five times. The first answer is never the real cause.",
        "company": "Toyota",
        "story": "A Toyota factory floor had an oil puddle. Why? Machine leaking. Why? Pump failing. Why? Worn bearing. Why? No filter. Why? No maintenance schedule. The fix was a $2 filter. Not a new machine.",
        "data": "Toyota's defect rate is 0.7 per 100 vehicles. The industry average is 1.5."
    },
    {
        "model": "Dogfooding",
        "what": "Use your own product before shipping it to customers.",
        "company": "Microsoft",
        "story": "Microsoft engineers were required to run Windows on their own machines months before release. Bugs that survived internal use were inexcusable. Companies that don't dogfood ship embarrassments.",
        "data": "Windows 95 had 11 million copies sold in 4 weeks. Dogfooding cut critical bugs by 40%."
    },
    {
        "model": "70-20-10 Rule",
        "what": "Allocate 70% of resources to core business, 20% to adjacent bets, 10% to moonshots.",
        "company": "Google",
        "story": "Gmail started as a 20% project. Google News started as a 20% project. AdSense started as a 20% project. The 10% moonshots became Google X, Waymo, and DeepMind.",
        "data": "Products from 20% time generated billions in revenue. Google formalised this in 2004."
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
    """Estimate total posts so far today based on UTC hour."""
    hour = datetime.now(timezone.utc).hour
    return 0 if hour < 18 else (1 if hour < 22 else 2)


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
