"""
Flask application for Villa Sirene concierge chatbot.

Routes:
    GET  /           — serves the chat UI
    POST /api/chat   — receives a user message, returns the bot response
    POST /api/reset  — resets the conversation state
"""

import os
import uuid
from flask import Flask, render_template, request, jsonify, make_response

from database import init_db
from chatbot import process_message, IDLE

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotel.db")

sessions = {}


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

    resp = make_response(jsonify({"response": response_text}))
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


if __name__ == "__main__":
    init_db(DB_PATH)
    app.run(host="0.0.0.0", port=5000, debug=False)
