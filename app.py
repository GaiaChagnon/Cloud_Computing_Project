"""
Flask application for Villa Sirene concierge chatbot.

Routes:
    GET  /            — serves the chat UI
    POST /api/chat    — receives a user message, returns the bot response
    POST /api/reset   — resets the conversation state
    POST /api/lookup  — look up a reservation by confirmation code or ID
"""

import os
import re
import uuid
from datetime import datetime
from flask import Flask, render_template, request, jsonify, make_response

import database as db
from chatbot import process_message, IDLE

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotel.db")

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

    response_text, new_state, new_data = process_message(
        user_msg, session["state"], session["data"], DB_PATH
    )
    session["state"] = new_state
    session["data"] = new_data

    result = {"response": response_text}

    if "has been confirmed" in response_text:
        code_match = re.search(r"VS-[A-Z0-9]{6}", response_text)
        if code_match:
            res = db.find_reservation_by_code(DB_PATH, code_match.group())
            if res:
                nights = (datetime.strptime(res["check_out"], "%Y-%m-%d")
                          - datetime.strptime(res["check_in"], "%Y-%m-%d")).days
                result["event"] = "booking_confirmed"
                result["confirmation"] = {
                    "code": res["confirmation_code"],
                    "guest_name": res["full_name"],
                    "room_type": res["room_type"],
                    "room_number": res["room_number"],
                    "check_in": res["check_in"],
                    "check_out": res["check_out"],
                    "nights": nights,
                    "total_price": res["total_price"],
                    "email": _mask_email(res["email"]),
                }

    if "has been updated" in response_text:
        result["event"] = "booking_modified"
    if "has been cancelled" in response_text:
        result["event"] = "booking_cancelled"

    resp = make_response(jsonify(result))
    resp.set_cookie("sid", sid, httponly=True, samesite="Lax")
    return resp


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

    room_labels = {
        "classic": "Classic", "superior": "Superior", "deluxe": "Deluxe",
        "suite": "Suite", "penthouse": "Penthouse Suite",
    }

    return jsonify({
        "found": True,
        "reservation": {
            "confirmation_code": res["confirmation_code"],
            "guest_name": res["full_name"],
            "room_type": room_labels.get(res["room_type"], res["room_type"].title()),
            "room_number": res["room_number"],
            "check_in": res["check_in"],
            "check_out": res["check_out"],
            "nights": nights,
            "total_price": res["total_price"],
            "status": res["status"],
            "email": _mask_email(res["email"]),
        }
    })


if __name__ == "__main__":
    init_db_path = DB_PATH
    db.init_db(init_db_path)
    app.run(host="0.0.0.0", port=5000, debug=False)
