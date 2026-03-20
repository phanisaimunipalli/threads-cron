"""
Vercel serverless function — generates and posts to Threads 3x daily.
Triggered by GitHub Actions at 7:30 AM, 12:30 PM, 6:30 PM PST.
Each post alternates: text post, image card, text post, image card...
"""

import os
import json
import time
import base64
import hashlib
import textwrap
import urllib.request
import urllib.parse
from datetime import datetime, date, timezone, timedelta
from http.server import BaseHTTPRequestHandler


# ── Config ────────────────────────────────────────────────────────────────────

GEMINI_API_KEY   = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL     = "gemini-3.1-flash-lite-preview"

THREADS_TOKEN    = os.environ.get("THREADS_ACCESS_TOKEN")
THREADS_USER_ID  = os.environ.get("THREADS_USER_ID")
THREADS_API      = "https://graph.threads.net/v1.0"

CLOUDINARY_CLOUD = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_PRESET= os.environ.get("CLOUDINARY_UPLOAD_PRESET")

CRON_SECRET      = os.environ.get("CRON_SECRET", "")


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
- Single post: 150-300 characters, line breaks for readability
- No emojis unless they genuinely add meaning (rare)"""

FORMATS = [
    {
        "name": "short_punchy",
        "instruction": "Write a SHORT post (100-200 characters). One bold claim. Two tight sentences max. Each line hits hard. No filler."
    },
    {
        "name": "dense_long",
        "instruction": "Write a LONGER dense post (300-500 characters). No line breaks. One continuous paragraph. Pack in the insight. Write like you're explaining something important to a smart friend in a message."
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


# ── Content generation ────────────────────────────────────────────────────────

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


def get_format(post_number):
    """Rotate formats across posts. post_number cycles through formats."""
    idx = post_number % len(FORMATS)
    return FORMATS[idx]


def refine_draft(draft):
    prompt = f"""You are a Threads engagement editor. Make this post land harder.

Original post:
\"\"\"{draft}\"\"\"

Rules:
- Rewrite the opening line to create tension or curiosity. It must stop the scroll.
- Tighten every line. Cut filler. Shorten sentences. Remove anything that doesn't earn its place.
- Keep the core insight and voice intact. Do NOT change the meaning or make it generic.
- Open with "I" if it fits naturally.
- Stay under 300 characters total.
- No emojis, no hashtags, no LinkedIn tone.
- CRITICAL: Never use dashes ( - ) anywhere. Use a period or line break instead.

Output only the rewritten post, nothing else."""
    return _gemini(prompt, temperature=0.7)


def generate_content(pillar, post_number=0):
    headlines = fetch_hn_headlines()
    headlines_str = "\n".join(f"- {h}" for h in headlines) if headlines else "No headlines available."
    fmt = get_format(post_number)

    prompt = f"""{VOICE_PROMPT}

Today's content pillar: {pillar['name']}
Focus: {pillar['focus']}

Recent tech/AI headlines for context (use as inspiration, not to summarize):
{headlines_str}

Format for today: {fmt['name']}
{fmt['instruction']}

CRITICAL: Never use dashes ( - ) anywhere in the post.
Output only the post text, nothing else."""

    draft = _gemini(prompt)
    refined = refine_draft(draft)
    return refined, fmt["name"]


# ── Image generation ──────────────────────────────────────────────────────────

def get_font(size):
    """Download and cache Inter font, fall back to default."""
    from PIL import ImageFont
    font_path = "/tmp/inter.ttf"
    if not os.path.exists(font_path):
        try:
            url = "https://github.com/rsms/inter/raw/master/docs/font-files/Inter-SemiBold.ttf"
            urllib.request.urlretrieve(url, font_path)
        except Exception:
            return ImageFont.load_default()
    try:
        return ImageFont.truetype(font_path, size)
    except Exception:
        return ImageFont.load_default()


def generate_image_card(text):
    """Generate a clean dark text card. Returns PNG bytes."""
    from PIL import Image, ImageDraw

    W, H = 1080, 1080
    BG      = "#0A0A0A"
    TEXT_C  = "#FFFFFF"
    ACCENT  = "#4F8EF7"
    HANDLE  = "@iamphanisairam"

    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Accent bar at top
    draw.rectangle([80, 80, 180, 86], fill=ACCENT)

    # Main text
    font_main   = get_font(52)
    font_handle = get_font(32)

    margin  = 80
    max_w   = W - margin * 2
    wrapped = textwrap.fill(text, width=32)
    lines   = wrapped.split("\n")

    # Calculate total text height to center vertically
    line_h  = 70
    total_h = len(lines) * line_h
    y       = (H - total_h) // 2 - 40

    for line in lines:
        draw.text((margin, y), line, font=font_main, fill=TEXT_C)
        y += line_h

    # Handle at bottom right
    draw.text((W - margin, H - 80), HANDLE, font=font_handle, fill=ACCENT, anchor="ra")

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def upload_to_cloudinary(image_bytes):
    """Upload image bytes to Cloudinary, return public URL."""
    if not CLOUDINARY_CLOUD or not CLOUDINARY_PRESET:
        return None

    b64 = base64.b64encode(image_bytes).decode()
    data = urllib.parse.urlencode({
        "file": f"data:image/png;base64,{b64}",
        "upload_preset": CLOUDINARY_PRESET,
    }).encode("utf-8")

    url = f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD}/image/upload"
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read())
    return result.get("secure_url")


# ── Threads posting ───────────────────────────────────────────────────────────

def _threads_post(url, data):
    encoded = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=encoded, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def post_text(text):
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


def post_image(image_url, caption):
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads", {
        "media_type": "IMAGE",
        "image_url": image_url,
        "text": caption,
        "access_token": THREADS_TOKEN,
    })
    time.sleep(2)
    result = _threads_post(f"{THREADS_API}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": result["id"],
        "access_token": THREADS_TOKEN,
    })
    return result["id"]


# ── Vercel handler ────────────────────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        auth = self.headers.get("authorization", "")
        if CRON_SECRET and auth != f"Bearer {CRON_SECRET}":
            self._respond(401, {"error": "Unauthorized"})
            return

        try:
            pillar = get_today_pillar()

            # Post number = total posts today (0, 1, 2) based on UTC hour
            hour = datetime.now(timezone.utc).hour
            post_number = 0 if hour < 18 else (1 if hour < 22 else 2)

            content, fmt_name = generate_content(pillar, post_number)

            # Alternate: even post_number = image card, odd = text only
            post_type = "image" if post_number % 2 == 0 and CLOUDINARY_CLOUD else "text"
            thread_id = None

            if post_type == "image":
                try:
                    img_bytes = generate_image_card(content)
                    img_url   = upload_to_cloudinary(img_bytes)
                    if img_url:
                        thread_id = post_image(img_url, content)
                    else:
                        post_type = "text"
                except Exception:
                    post_type = "text"

            if post_type == "text" or not thread_id:
                thread_id = post_text(content)
                post_type = "text"

            self._respond(200, {
                "ok": True,
                "pillar": pillar["name"],
                "format": fmt_name,
                "type": post_type,
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
