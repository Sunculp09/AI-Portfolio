"""
emailer.py - automatic emails to the recruiter after you approve or decline.

Uses Brevo's HTTPS API (not SMTP), so it also works on Render's free tier,
which blocks SMTP ports. Needs these values in .env:
    BREVO_API_KEY=...
    SENDER_EMAIL=...        (the sender you verified in Brevo)
Optional:
    SENDER_NAME=...         (defaults to your name)
    REPLY_TO_EMAIL=...      (defaults to SENDER_EMAIL)
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from config import INTERVIEW_TYPES, OWNER_NAME, OWNER_TZ

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _local_time(iso, tz_name):
    """Show the interview time in the recruiter's own timezone."""
    try:
        tz = ZoneInfo(tz_name) if tz_name else ZoneInfo(OWNER_TZ)
    except Exception:
        tz = ZoneInfo(OWNER_TZ)
    local = datetime.fromisoformat(iso).astimezone(tz)
    return local.strftime("%A, %d %B %Y at %I:%M %p") + f" ({tz.key})"


def build_decision_email(booking, status):
    """Return (subject, text) for a confirmed or declined booking."""
    name = booking["recruiter_name"]
    kind = booking["interview_type"]
    when = _local_time(booking["start_utc"], booking.get("recruiter_timezone"))
    minutes = INTERVIEW_TYPES.get(kind, "")
    footer = (
        f"\n\nBest regards,\n{OWNER_NAME}\n\n"
        "This message was sent by Sunculp's AI scheduling assistant."
    )

    if status == "confirmed":
        subject = f"Interview confirmed: {kind} round with {OWNER_NAME}"
        text = (
            f"Hello {name},\n\n"
            f"Good news. {OWNER_NAME} has confirmed your {kind} interview "
            f"for the {booking['role']} role at {booking['company']}.\n\n"
            f"When: {when}\n"
            f"Duration: {minutes} minutes\n\n"
            "Please reply to this email with the meeting link or platform you would like to use."
            + footer
        )
    else:
        subject = f"Update on your interview request with {OWNER_NAME}"
        text = (
            f"Hello {name},\n\n"
            f"Thank you for your interest. Unfortunately, {OWNER_NAME} is not able to take "
            f"the {kind} interview for the {booking['role']} role on {when}.\n\n"
            "You are welcome to request another time through the portfolio chat, "
            "or reply to this email."
            + footer
        )
    return subject, text


def send_email(to_email, to_name, subject, text, post=None):
    """Send one email through Brevo. Returns (ok, info)."""
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("BREVO_API_KEY")
    sender = os.getenv("SENDER_EMAIL")
    if not api_key or not sender:
        return False, "BREVO_API_KEY or SENDER_EMAIL is missing in .env"

    if post is None:
        import httpx  # installed together with the groq package

        post = httpx.post

    payload = {
        "sender": {"name": os.getenv("SENDER_NAME") or OWNER_NAME, "email": sender},
        "to": [{"email": to_email, "name": to_name}],
        "replyTo": {"email": os.getenv("REPLY_TO_EMAIL") or sender},
        "subject": subject,
        "textContent": text,
    }
    copy_to = os.getenv("COPY_TO_EMAIL") or sender
    payload["bcc"] = [{"email": copy_to}]

    try:
        response = post(
            BREVO_URL,
            headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
            json=payload,
            timeout=20,
        )
    except Exception as exc:
        return False, f"network error: {exc}"

    if 200 <= response.status_code < 300:
        return True, "sent"
    return False, f"Brevo error {response.status_code}: {response.text[:200]}"


def send_decision_email(booking, status, post=None):
    subject, text = build_decision_email(booking, status)
    return send_email(booking["recruiter_email"], booking["recruiter_name"], subject, text, post=post)
