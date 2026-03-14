"""
Flask application for Villa Sirene concierge chatbot.

Routes:
    GET  /            — serves the chat UI
    POST /api/chat    — receives a user message, returns the bot response
    POST /api/reset   — resets the conversation state
    POST /api/lookup  — look up a reservation by confirmation code or ID
    GET  /api/rooms   — return room type catalogue
    GET  /health      — health check
"""

import os
import re
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, make_response

import database as db
import email_service
from chatbot import process_message, IDLE, RES_CONFIRM, MOD_CONFIRM, CANCEL_CONFIRM, ROOM_INFO

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotel.db")

ROOM_LABELS = {
    "classic": "Classic", "superior": "Superior", "deluxe": "Deluxe",
    "suite": "Suite", "penthouse": "Penthouse Suite",
}

sessions = {}


def _mask_email(email):
    try:
        user, domain = email.split("@")
        masked = user[0] + "***" + (user[-1] if len(user) > 2 else "")
        return f"{masked}@{domain}"
    except Exception:
        return "***@***.***"


def _get_session(req):
    """Retrieve or create a server-side session keyed by a cookie."""
    sid = req.cookies.get("sid")
    if sid and sid in sessions:
        return sid, sessions[sid]
    sid = uuid.uuid4().hex
    sessions[sid] = {"state": IDLE, "data": {}}
    return sid, sessions[sid]


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    sid, session = _get_session(request)
    user_msg = (request.json or {}).get("message", "").strip()

    if not user_msg:
        resp = make_response(jsonify({"response": "I did not catch that. Could you please type your message?"}))
        resp.set_cookie("sid", sid, httponly=True, samesite="Lax")
        return resp

    old_state = session["state"]
    old_data = dict(session["data"])

    response_text, new_state, new_data = process_message(
        user_msg, old_state, session["data"], DB_PATH
    )
    session["state"] = new_state
    session["data"] = new_data

    result = {"response": response_text}

    _handle_email_events(result, response_text, old_state, old_data)

    resp = make_response(jsonify(result))
    resp.set_cookie("sid", sid, httponly=True, samesite="Lax")
    return resp


def _handle_email_events(result, response_text, old_state, old_data):
    """Detect booking events and trigger real emails + frontend metadata."""

    if "has been confirmed" in response_text and old_state == RES_CONFIRM:
        code_match = re.search(r"VS-[A-Z0-9]{6}", response_text)
        if not code_match:
            return
        res = db.find_reservation_by_code(DB_PATH, code_match.group())
        if not res:
            return

        nights = (datetime.strptime(res["check_out"], "%Y-%m-%d")
                  - datetime.strptime(res["check_in"], "%Y-%m-%d")).days
        room_label = ROOM_LABELS.get(res["room_type"], res["room_type"].title())

        result["event"] = "booking_confirmed"
        result["confirmation"] = {
            "code": res["confirmation_code"],
            "guest_name": res["full_name"],
            "room_type": room_label,
            "room_number": res["room_number"],
            "check_in": res["check_in"],
            "check_out": res["check_out"],
            "nights": nights,
            "total_price": res["total_price"],
            "email": _mask_email(res["email"]),
        }

        raw_email = old_data.get("email") or res["email"]
        email_service.send_confirmation(
            raw_email, res["full_name"], res["confirmation_code"],
            room_label, res["room_number"],
            res["check_in"], res["check_out"], nights, res["total_price"],
        )
        return

    if "has been updated" in response_text and old_state == MOD_CONFIRM:
        result["event"] = "booking_modified"
        reservation = old_data.get("reservation", {})
        raw_email = reservation.get("email", "")
        code = reservation.get("confirmation_code", "")
        name = reservation.get("full_name", "Guest")
        if raw_email and code:
            updated_res = db.find_reservation_by_code(DB_PATH, code)
            changes = []
            if updated_res:
                rl = ROOM_LABELS.get(updated_res["room_type"], updated_res["room_type"].title())
                n = (datetime.strptime(updated_res["check_out"], "%Y-%m-%d")
                     - datetime.strptime(updated_res["check_in"], "%Y-%m-%d")).days
                changes = [
                    ("Room", f"{rl} (Room {updated_res['room_number']})"),
                    ("Check-in", updated_res["check_in"]),
                    ("Check-out", updated_res["check_out"]),
                    ("Duration", f"{n} night{'s' if n != 1 else ''}"),
                    ("Total", f"EUR {updated_res['total_price']:,.0f}"),
                    ("Confirmation", code),
                ]
            email_service.send_modification(raw_email, name, code, changes)
        return

    if "has been cancelled" in response_text and old_state == CANCEL_CONFIRM:
        result["event"] = "booking_cancelled"
        reservation = old_data.get("reservation", {})
        raw_email = reservation.get("email", "")
        code = reservation.get("confirmation_code", "")
        name = reservation.get("full_name", "Guest")
        if raw_email and code:
            email_service.send_cancellation(raw_email, name, code)
        return


@app.route("/api/reset", methods=["POST"])
def reset():
    sid, session = _get_session(request)
    session["state"] = IDLE
    session["data"] = {}
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("sid", sid, httponly=True, samesite="Lax")
    return resp


@app.route("/api/lookup", methods=["POST"])
def lookup():
    """Look up a reservation by confirmation code or ID/passport number."""
    data = request.json or {}
    code = data.get("confirmation_code", "").strip()
    id_num = data.get("id_number", "").strip()

    res = None
    if code:
        res = db.find_reservation_by_code(DB_PATH, code)
    elif id_num:
        res = db.find_reservation_by_id(DB_PATH, id_num)

    if not res:
        return jsonify({"found": False})

    nights = (datetime.strptime(res["check_out"], "%Y-%m-%d")
              - datetime.strptime(res["check_in"], "%Y-%m-%d")).days

    return jsonify({
        "found": True,
        "reservation": {
            "confirmation_code": res["confirmation_code"],
            "guest_name": res["full_name"],
            "room_type": ROOM_LABELS.get(res["room_type"], res["room_type"].title()),
            "room_number": res["room_number"],
            "check_in": res["check_in"],
            "check_out": res["check_out"],
            "nights": nights,
            "total_price": res["total_price"],
            "status": res["status"],
            "email": _mask_email(res["email"]),
        }
    })


@app.route("/api/rooms")
def rooms():
    """Return room type catalogue for the showcase page."""
    summary = db.get_room_type_summary(DB_PATH)
    return jsonify(summary)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "service": "villa-sirene-concierge"})


if __name__ == "__main__":
    db.init_db(DB_PATH)
    app.run(host="0.0.0.0", port=5000, debug=False)
