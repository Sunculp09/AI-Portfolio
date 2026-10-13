"""
tools.py - the actions the agent can take.

The LLM never touches the database or the calendar directly. It can only ask
for one of these functions to run. All real decisions (is this slot free? is
this email valid?) are made here, in plain Python, so the agent cannot invent
availability.
"""

import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config import AVAILABILITY, INTERVIEW_TYPES, OWNER_TZ, SCREENING

DB_PATH = os.getenv("BOOKINGS_DB", "bookings.db")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ACTIVE_STATUSES = ("pending_approval", "confirmed")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY,
    recruiter_name TEXT, recruiter_email TEXT, company TEXT, role TEXT,
    interview_type TEXT, start_utc TEXT, end_utc TEXT,
    status TEXT, created_at TEXT, recruiter_timezone TEXT
);
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY,
    recruiter_name TEXT, recruiter_email TEXT, company TEXT, message TEXT,
    created_at TEXT
);
"""


@contextmanager
def _db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    # Older databases lack the timezone column, so add it once.
    columns = [row["name"] for row in con.execute("PRAGMA table_info(bookings)")]
    if "recruiter_timezone" not in columns:
        con.execute("ALTER TABLE bookings ADD COLUMN recruiter_timezone TEXT")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _now():
    return datetime.now(timezone.utc)


# Optional hook: telegram_bot.py registers a function here to alert Sunculp.
_notifier = None


def set_notifier(fn):
    global _notifier
    _notifier = fn


def _notify(event, data):
    if _notifier:
        try:
            _notifier(event, data)
        except Exception as exc:  # an alert failure must never break a booking
            print("Notifier error:", exc)


def _parse_hm(text):
    h, m = text.split(":")
    return int(h), int(m)


def _busy_windows(con):
    rows = con.execute(
        "SELECT start_utc, end_utc FROM bookings WHERE status IN (?, ?)", ACTIVE_STATUSES
    ).fetchall()
    return [
        (datetime.fromisoformat(r["start_utc"]), datetime.fromisoformat(r["end_utc"]))
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Slot generation (the core scheduling logic)
# ---------------------------------------------------------------------------
def _all_free_slots(interview_type):
    """Return every valid start time (UTC datetimes) for the given interview type."""
    a = AVAILABILITY
    owner = ZoneInfo(OWNER_TZ)
    duration = timedelta(minutes=INTERVIEW_TYPES[interview_type])
    buffer = timedelta(minutes=a["buffer_minutes"])
    step = timedelta(minutes=a["step_minutes"])
    earliest = _now() + timedelta(hours=a["min_notice_hours"])
    sh, sm = _parse_hm(a["start"])
    eh, em = _parse_hm(a["end"])

    with _db() as con:
        busy = _busy_windows(con)

    per_day = {}
    for bs, _ in busy:
        d = bs.astimezone(owner).date()
        per_day[d] = per_day.get(d, 0) + 1

    first_day = earliest.astimezone(owner).date()
    slots = []
    for offset in range(a["horizon_days"] + 1):
        day = first_day + timedelta(days=offset)
        if day.weekday() not in a["working_days"]:
            continue
        if per_day.get(day, 0) >= a["max_per_day"]:
            continue

        blocked = []
        for b_start, b_end in a["blocked"]:
            bh, bm = _parse_hm(b_start)
            ch, cm = _parse_hm(b_end)
            blocked.append((
                datetime(day.year, day.month, day.day, bh, bm, tzinfo=owner),
                datetime(day.year, day.month, day.day, ch, cm, tzinfo=owner),
            ))

        t = datetime(day.year, day.month, day.day, sh, sm, tzinfo=owner)
        day_end = datetime(day.year, day.month, day.day, eh, em, tzinfo=owner)
        while t + duration <= day_end:
            s, e = t, t + duration
            ok = s >= earliest
            ok = ok and not any(s < b_end and e > b_start for b_start, b_end in blocked)
            ok = ok and not any(s < be + buffer and e + buffer > bs for bs, be in busy)
            if ok:
                slots.append(s.astimezone(timezone.utc))
            t += step
    return slots


def _spread(slots, count):
    """Pick slots from different days first, so the recruiter sees real variety."""
    owner = ZoneInfo(OWNER_TZ)
    by_day = {}
    for s in slots:
        by_day.setdefault(s.astimezone(owner).date(), []).append(s)
    days = [by_day[d] for d in sorted(by_day)]
    picked, rnd = [], 0
    while len(picked) < count and any(rnd < len(d) for d in days):
        for d in days:
            if rnd < len(d) and len(picked) < count:
                picked.append(d[rnd])
        rnd += 1
    return sorted(picked)


# ---------------------------------------------------------------------------
# Tool 1: check_fit
# ---------------------------------------------------------------------------
def check_fit(role, company=None, work_mode=None, location=None):
    role_l = (role or "").lower()
    role_match = any(k in role_l for k in SCREENING["target_roles"])
    mode_ok = work_mode is None or work_mode.lower() in SCREENING["work_modes"]
    prefs = [p.lower() for p in SCREENING["preferred_locations"]]
    loc_ok = not prefs or location is None or any(p in location.lower() for p in prefs)

    reasons = []
    if not role_match:
        reasons.append("Role is outside Sunculp's target areas (data analytics, AI engineering, business analysis).")
    if not mode_ok:
        reasons.append("Work mode is not one Sunculp has listed.")
    if not loc_ok:
        reasons.append("Location is outside Sunculp's preferred locations.")

    decision = "proceed" if not reasons else "needs_owner_review"
    return {"decision": decision, "reasons": reasons}


# ---------------------------------------------------------------------------
# Tool 2: get_available_slots
# ---------------------------------------------------------------------------
def get_available_slots(interview_type="hr", recruiter_timezone=None, count=3):
    if interview_type not in INTERVIEW_TYPES:
        return {"error": f"interview_type must be one of {list(INTERVIEW_TYPES)}"}
    try:
        rtz = ZoneInfo(recruiter_timezone) if recruiter_timezone else ZoneInfo(OWNER_TZ)
    except Exception:
        return {"error": "Unknown timezone. Use an IANA name such as 'Europe/London' or 'Asia/Kolkata'."}

    count = max(1, min(int(count), 5))
    picked = _spread(_all_free_slots(interview_type), count)
    if not picked:
        return {"slots": [], "note": "No free slots in the next two weeks. Offer to pass a message to Sunculp."}

    return {
        "interview_type": interview_type,
        "duration_minutes": INTERVIEW_TYPES[interview_type],
        "timezone": str(rtz),
        "slots": [
            {
                "start_utc": s.isoformat(),
                "display": s.astimezone(rtz).strftime("%a %d %b %Y, %I:%M %p"),
            }
            for s in picked
        ],
    }


# ---------------------------------------------------------------------------
# Tool 3: book_interview
# ---------------------------------------------------------------------------
def book_interview(recruiter_name, recruiter_email, company, role, interview_type, slot_start_utc,
                   recruiter_timezone=None):
    if not (recruiter_name and company and role):
        return {"error": "recruiter_name, company and role are required."}
    if not EMAIL_RE.match(recruiter_email or ""):
        return {"error": "A valid recruiter_email is required."}
    if interview_type not in INTERVIEW_TYPES:
        return {"error": f"interview_type must be one of {list(INTERVIEW_TYPES)}"}
    if recruiter_timezone:
        try:
            ZoneInfo(recruiter_timezone)
        except Exception:
            return {"error": "Unknown timezone. Use an IANA name such as 'Europe/London'."}
    try:
        start = datetime.fromisoformat(slot_start_utc)
        if start.tzinfo is None:
            return {"error": "slot_start_utc must include a timezone offset."}
        start = start.astimezone(timezone.utc)
    except ValueError:
        return {"error": "slot_start_utc must be an ISO timestamp taken from get_available_slots."}

    # The slot must still be free right now. This blocks invented times and double booking.
    if start not in _all_free_slots(interview_type):
        return {"error": "That slot is not available. Call get_available_slots again and offer new options."}

    end = start + timedelta(minutes=INTERVIEW_TYPES[interview_type])
    booking_id = uuid.uuid4().hex[:8]
    with _db() as con:
        con.execute(
            "INSERT INTO bookings (id, recruiter_name, recruiter_email, company, role, interview_type, "
            "start_utc, end_utc, status, created_at, recruiter_timezone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (booking_id, recruiter_name, recruiter_email, company, role, interview_type,
             start.isoformat(), end.isoformat(), "pending_approval", _now().isoformat(),
             recruiter_timezone),
        )
    _notify("booking", {
        "id": booking_id, "recruiter_name": recruiter_name, "recruiter_email": recruiter_email,
        "company": company, "role": role, "interview_type": interview_type,
        "start_utc": start.isoformat(),
    })
    return {
        "booking_id": booking_id,
        "status": "pending_approval",
        "message": "Request recorded. It is confirmed only after Sunculp approves it.",
    }


# ---------------------------------------------------------------------------
# Tool 4: leave_message
# ---------------------------------------------------------------------------
def leave_message(recruiter_name, recruiter_email, company, message):
    if not EMAIL_RE.match(recruiter_email or ""):
        return {"error": "A valid recruiter_email is required."}
    with _db() as con:
        con.execute(
            "INSERT INTO leads VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex[:8], recruiter_name, recruiter_email, company, message, _now().isoformat()),
        )
    _notify("lead", {
        "recruiter_name": recruiter_name, "recruiter_email": recruiter_email,
        "company": company, "message": message,
    })
    return {"status": "saved", "message": "Message saved for Sunculp to review personally."}


# ---------------------------------------------------------------------------
# Booking status (used by Telegram approval and by the recruiter status tool)
# ---------------------------------------------------------------------------
def get_booking(booking_id):
    with _db() as con:
        row = con.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    return dict(row) if row else None


def set_booking_status(booking_id, new_status):
    """Approve or decline. Only a pending booking can change. Returns True if it changed."""
    if new_status not in ("confirmed", "declined"):
        return False
    with _db() as con:
        cur = con.execute(
            "UPDATE bookings SET status = ? WHERE id = ? AND status = 'pending_approval'",
            (new_status, booking_id),
        )
        changed = cur.rowcount == 1
    return changed


def check_booking_status(booking_id, recruiter_email):
    booking = get_booking(booking_id)
    if not booking or booking["recruiter_email"].lower() != (recruiter_email or "").strip().lower():
        return {"error": "No booking found for that booking id and email."}
    return {
        "booking_id": booking["id"],
        "status": booking["status"],
        "interview_type": booking["interview_type"],
        "start_utc": booking["start_utc"],
    }


# ---------------------------------------------------------------------------
# Tool registry: schemas the LLM sees + dispatcher
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "check_fit",
            "description": "Screen an opportunity against Sunculp's target roles, work mode and location. Call this BEFORE offering any interview slot.",
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {"type": "string", "description": "Job title offered"},
                    "company": {"type": "string"},
                    "work_mode": {"type": "string", "description": "remote, hybrid or onsite"},
                    "location": {"type": "string"},
                },
                "required": ["role"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_slots",
            "description": "Get up to 3 real free interview slots from Sunculp's availability rules. Never invent times; only use slots returned here.",
            "parameters": {
                "type": "object",
                "properties": {
                    "interview_type": {"type": "string", "enum": list(INTERVIEW_TYPES)},
                    "recruiter_timezone": {"type": "string", "description": "IANA name, e.g. Europe/London"},
                    "count": {"type": "integer", "description": "1 to 5, default 3"},
                },
                "required": ["interview_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_interview",
            "description": "Book the slot the recruiter chose. Requires name, email, company, role, interview type and the exact start_utc value from get_available_slots.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recruiter_name": {"type": "string"},
                    "recruiter_email": {"type": "string"},
                    "company": {"type": "string"},
                    "role": {"type": "string"},
                    "interview_type": {"type": "string", "enum": list(INTERVIEW_TYPES)},
                    "slot_start_utc": {"type": "string", "description": "Exact start_utc value of the chosen slot"},
                    "recruiter_timezone": {"type": "string", "description": "Recruiter's IANA timezone, e.g. Europe/London"},
                },
                "required": ["recruiter_name", "recruiter_email", "company", "role", "interview_type", "slot_start_utc"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_booking_status",
            "description": "Check whether a booking is pending_approval, confirmed or declined. Needs the booking_id from the earlier booking result and the recruiter's email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_id": {"type": "string"},
                    "recruiter_email": {"type": "string"},
                },
                "required": ["booking_id", "recruiter_email"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "leave_message",
            "description": "Save a message for Sunculp when the opportunity needs his personal review or no slot works.",
            "parameters": {
                "type": "object",
                "properties": {
                    "recruiter_name": {"type": "string"},
                    "recruiter_email": {"type": "string"},
                    "company": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["recruiter_name", "recruiter_email", "company", "message"],
            },
        },
    },
]

_REGISTRY = {
    "check_fit": check_fit,
    "get_available_slots": get_available_slots,
    "book_interview": book_interview,
    "leave_message": leave_message,
    "check_booking_status": check_booking_status,
}


def execute_tool(name, arguments_json):
    """Run a tool requested by the LLM. Always returns a dict, never raises."""
    fn = _REGISTRY.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        args = json.loads(arguments_json or "{}")
        return fn(**args)
    except TypeError as exc:
        return {"error": f"Invalid arguments: {exc}"}
    except Exception as exc:  # keep the agent alive on any tool failure
        return {"error": f"Tool failed: {exc}"}
