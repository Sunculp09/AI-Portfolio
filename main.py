"""
main.py - FastAPI server. Replaces your old backend file.

Fixes over the old version:
  - Each visitor gets their own conversation (session_id), no shared global list.
  - Old history is trimmed and expired, so memory does not grow forever.
  - Basic per-IP rate limit protects your Groq usage.
  - Errors are handled, so a failed call never leaves a broken history.
The /chat stream format is unchanged, so your HTML keeps working.
"""

import json
import os
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from groq import Groq
from pydantic import BaseModel, Field

from agent import build_system_prompt, run_agent
from telegram_bot import start_bot

load_dotenv()
API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise ValueError("API key is missing.")

client = Groq(api_key=API_KEY)
MODEL = "openai/gpt-oss-120b"

with open("candidate.json", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = build_system_prompt(json.load(f))

@asynccontextmanager
async def lifespan(app):
    start_bot()  # starts Telegram approval alerts (skipped if not configured)
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to your portfolio domain once deployed
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Sessions and rate limiting (in memory; fine for a single-instance portfolio)
# ---------------------------------------------------------------------------
SESSIONS = {}              # session_id -> {"history": [...], "last": timestamp}
SESSION_TTL = 60 * 60      # forget a visitor after 1 hour of silence
MAX_HISTORY = 40           # messages kept per visitor
RATE = {}                  # ip -> list of request timestamps
RATE_LIMIT = 15            # requests per minute per IP


def get_history(session_id):
    now = time.time()
    for sid in [s for s, v in SESSIONS.items() if now - v["last"] > SESSION_TTL]:
        del SESSIONS[sid]
    session = SESSIONS.setdefault(session_id, {"history": [], "last": now})
    session["last"] = now
    return session["history"]


def trim(history):
    """Drop oldest messages, always cutting at a user message so tool pairs stay intact."""
    while len(history) > MAX_HISTORY:
        history.pop(0)
        while history and history[0]["role"] != "user":
            history.pop(0)


def rate_limited(request: Request):
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "?")
    now = time.time()
    recent = [t for t in RATE.get(ip, []) if now - t < 60]
    recent.append(now)
    RATE[ip] = recent
    return len(recent) > RATE_LIMIT


def sse(payload):
    return f"data: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


@app.get("/")
def home():
    return {"message": "AI Portfolio Agent is running"}


@app.post("/chat")
def chat(body: ChatRequest, request: Request):
    if rate_limited(request):
        return JSONResponse({"error": "Too many requests. Please wait a minute."}, status_code=429)

    history = get_history(body.session_id or uuid.uuid4().hex)
    checkpoint = len(history)
    history.append({"role": "user", "content": body.message})

    def stream():
        try:
            answer = run_agent(client, MODEL, SYSTEM_PROMPT, history)
        except Exception as exc:
            del history[checkpoint:]  # roll back so history stays valid
            print("Agent error:", exc)
            yield sse({"content": "Sorry, something went wrong on my side. Please try again."})
            yield sse({"done": True})
            return

        trim(history)
        words = answer.split(" ")
        for i in range(0, len(words), 3):  # send in small chunks so the UI types it out
            piece = " ".join(words[i:i + 3]) + (" " if i + 3 < len(words) else "")
            yield sse({"content": piece})
        yield sse({"done": True})

    return StreamingResponse(stream(), media_type="text/event-stream")
