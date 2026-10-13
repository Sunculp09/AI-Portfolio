"""
telegram_bot.py - Phase 2: instant alerts and approval from your phone.

Flow:
  1. A recruiter books a slot, so tools.py calls the notifier registered here.
  2. You get a Telegram message with Approve and Decline buttons.
  3. You tap a button, so the booking status becomes confirmed or declined.

It uses long polling in a background thread, so it needs no public URL and
works on localhost and on Render. Only YOUR chat id can approve or decline.
"""

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import emailer
import tools
from config import OWNER_TZ

_started = False


def _api(token, method, payload=None, timeout=40):
    import httpx  # installed together with the groq package

    response = httpx.post(
        f"https://api.telegram.org/bot{token}/{method}", json=payload or {}, timeout=timeout
    )
    return response.json()


def _when(iso):
    local = datetime.fromisoformat(iso).astimezone(ZoneInfo(OWNER_TZ))
    return local.strftime("%a %d %b %Y, %I:%M %p") + f" ({OWNER_TZ})"


def format_booking_alert(d):
    return (
        "New interview request\n\n"
        f"Recruiter: {d['recruiter_name']} ({d['recruiter_email']})\n"
        f"Company: {d['company']}\n"
        f"Role: {d['role']}\n"
        f"Type: {d['interview_type']}\n"
        f"When: {_when(d['start_utc'])}\n"
        f"Booking id: {d['id']}"
    )


def format_lead_alert(d):
    return (
        "New message needs your review\n\n"
        f"Recruiter: {d['recruiter_name']} ({d['recruiter_email']})\n"
        f"Company: {d['company']}\n"
        f"Message: {d['message']}"
    )


def make_notifier(token, chat_id, api=_api):
    """Return the function tools.py calls whenever something needs your attention."""

    def notify(event, data):
        if event == "booking":
            payload = {
                "chat_id": chat_id,
                "text": format_booking_alert(data),
                "reply_markup": {
                    "inline_keyboard": [[
                        {"text": "Approve", "callback_data": f"approve:{data['id']}"},
                        {"text": "Decline", "callback_data": f"decline:{data['id']}"},
                    ]]
                },
            }
        elif event == "lead":
            payload = {"chat_id": chat_id, "text": format_lead_alert(data)}
        else:
            return
        # Send in a thread so the recruiter's chat never waits on Telegram.
        threading.Thread(target=lambda: api(token, "sendMessage", payload), daemon=True).start()

    return notify


def _make_mailer(token, chat_id, api=_api):
    """Return a function that emails the recruiter, then reports the result to you."""

    def mail(booking_id, status):
        def work():
            booking = tools.get_booking(booking_id)
            if not booking:
                return
            try:
                ok, info = emailer.send_decision_email(booking, status)
            except Exception as exc:  # report any failure instead of dying silently
                ok, info = False, str(exc)
            who = f"{booking['recruiter_name']} ({booking['recruiter_email']})"
            text = f"Email sent to {who}." if ok else f"Email to {who} FAILED: {info}"
            try:
                api(token, "sendMessage", {"chat_id": chat_id, "text": text})
            except Exception as exc:
                print("Telegram report failed:", exc)

        threading.Thread(target=work, daemon=True).start()

    return mail


def handle_callback(token, chat_id, callback, api=_api, mail=None):
    """Process a tap on Approve or Decline. Ignores anyone except the owner."""
    sender = str((callback.get("from") or {}).get("id", ""))
    if sender != str(chat_id):
        api(token, "answerCallbackQuery", {"callback_query_id": callback["id"], "text": "Not authorized"})
        return

    action, _, booking_id = (callback.get("data") or "").partition(":")
    status = {"approve": "confirmed", "decline": "declined"}.get(action)
    if not status or not booking_id:
        api(token, "answerCallbackQuery", {"callback_query_id": callback["id"], "text": "Unknown action"})
        return

    changed = tools.set_booking_status(booking_id, status)
    if changed:
        (mail or _make_mailer(token, chat_id, api))(booking_id, status)
    answer = f"Booking {status}" if changed else "Already processed"
    api(token, "answerCallbackQuery", {"callback_query_id": callback["id"], "text": answer})

    message = callback.get("message") or {}
    if changed and message:
        # Editing the text without a keyboard removes the buttons.
        api(token, "editMessageText", {
            "chat_id": chat_id,
            "message_id": message["message_id"],
            "text": message.get("text", "") + f"\n\nDecision: {status.upper()}",
        })


def _poll(token, chat_id):
    offset = None
    while True:
        try:
            payload = {"timeout": 30, "allowed_updates": ["callback_query"]}
            if offset:
                payload["offset"] = offset
            data = _api(token, "getUpdates", payload, timeout=45)
            if not data.get("ok"):
                print("Telegram polling error:", data.get("description"))
                time.sleep(10)  # also covers 409: the same bot polled from two places
                continue
            for update in data["result"]:
                offset = update["update_id"] + 1
                if update.get("callback_query"):
                    handle_callback(token, chat_id, update["callback_query"])
        except Exception as exc:
            print("Telegram polling exception:", exc)
            time.sleep(5)


def start_bot():
    global _started
    if _started:
        return
    from dotenv import load_dotenv

    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram disabled: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
        return
    _started = True
    tools.set_notifier(make_notifier(token, chat_id))
    threading.Thread(target=_poll, args=(token, chat_id), daemon=True).start()
    print("Telegram bot started")
