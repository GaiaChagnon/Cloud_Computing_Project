"""
Conversation engine for Villa Sirene concierge chatbot.

State-machine approach: each user message is processed against the current
conversation state, producing a response and a new state.  Sensitive data
(ID numbers, emails) is never echoed back in full.
"""

from datetime import datetime, date, timedelta
from dateutil import parser as date_parser
import database as db

# ---------------------------------------------------------------------------
# Conversation states
# ---------------------------------------------------------------------------
IDLE          = "IDLE"
RES_DATES_IN  = "RES_DATES_IN"
RES_DATES_OUT = "RES_DATES_OUT"
RES_ROOM      = "RES_ROOM"
RES_NAME      = "RES_NAME"
RES_ID        = "RES_ID"
RES_EMAIL     = "RES_EMAIL"
RES_CONFIRM   = "RES_CONFIRM"
MOD_ID        = "MOD_ID"
MOD_SELECT    = "MOD_SELECT"
MOD_DATES_IN  = "MOD_DATES_IN"
MOD_DATES_OUT = "MOD_DATES_OUT"
MOD_ROOM      = "MOD_ROOM"
MOD_CONFIRM   = "MOD_CONFIRM"
VIEW_ID       = "VIEW_ID"
CANCEL_ID     = "CANCEL_ID"
CANCEL_CONFIRM = "CANCEL_CONFIRM"

# ---------------------------------------------------------------------------
# Room catalogue
# ---------------------------------------------------------------------------
ROOM_INFO = {
    "classic":   {"label": "Classic",         "price": 180},
    "superior":  {"label": "Superior",        "price": 280},
    "deluxe":    {"label": "Deluxe",          "price": 420},
    "suite":     {"label": "Suite",           "price": 650},
    "penthouse": {"label": "Penthouse Suite", "price": 1200},
}

ROOM_DESCRIPTIONS = {
    "classic":   "Charming room with Mediterranean decor, terracotta floors, and a balcony overlooking the village.",
    "superior":  "Spacious retreat with hand-painted tiles, antique furnishings, and partial sea views.",
    "deluxe":    "Elegant room with panoramic sea views, marble bathroom, and sunset terrace.",
    "suite":     "Luxurious suite with separate living area, premium sea views, soaking tub, and garden terrace.",
    "penthouse": "Exclusive penthouse with wraparound terrace, 360 Amalfi Coast views, and private jacuzzi.",
}

# ---------------------------------------------------------------------------
# Privacy helpers
# ---------------------------------------------------------------------------

def _mask_email(email):
    try:
        user, domain = email.split("@")
        if len(user) <= 2:
            masked = user[0] + "***"
        else:
            masked = user[0] + "***" + user[-1]
        return f"{masked}@{domain}"
    except Exception:
        return "***@***.***"


def _mask_id(id_number):
    if len(id_number) <= 4:
        return "***" + id_number[-2:]
    return "***" + id_number[-4:]


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

def _parse_date(text):
    """Try to parse a human-readable date string. Returns a date object or None."""
    try:
        parsed = date_parser.parse(text, dayfirst=True)
        return parsed.date()
    except (ValueError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Intent detection (keyword-based)
# ---------------------------------------------------------------------------

def _detect_intent(msg):
    m = msg.lower().strip()

    cancel_kw  = ["cancel"]
    modify_kw  = ["modify", "change", "update", "edit", "modification"]
    view_kw    = ["view", "check", "look up", "find", "show", "status", "my reservation", "my booking"]
    reserve_kw = ["book", "reserve", "reservation", "new booking", "make a booking",
                  "would like a room", "need a room", "like to stay"]
    greet_kw   = ["hello", "hi", "hey", "good morning", "good afternoon",
                  "good evening", "buongiorno", "ciao", "greetings"]
    info_kw    = ["amenities", "restaurant", "pool", "spa", "beach", "wifi",
                  "parking", "shuttle", "pet", "dog", "check-in time",
                  "checkout time", "check-out time", "address", "location",
                  "direction", "price", "rate", "cost", "how much", "breakfast"]

    for kw in cancel_kw:
        if kw in m:
            return "CANCEL"
    for kw in modify_kw:
        if kw in m:
            return "MODIFY"
    for kw in view_kw:
        if kw in m:
            return "VIEW"
    for kw in reserve_kw:
        if kw in m:
            return "RESERVE"
    for kw in greet_kw:
        if m.startswith(kw) or m == kw:
            return "GREETING"
    for kw in info_kw:
        if kw in m:
            return "INFO"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Hotel FAQ
# ---------------------------------------------------------------------------

HOTEL_FAQ = (
    "Here is some useful information about Villa Sirene:\n\n"
    "**Location:** Via Cristoforo Colombo 30, 84017 Positano SA, Italy\n\n"
    "**Check-in:** from 3:00 PM  |  **Check-out:** by 11:00 AM\n\n"
    "**Amenities:** Private beach access, rooftop infinity pool, spa & wellness centre, "
    "Mediterranean restaurant *La Terrazza*, complimentary Wi-Fi, concierge service, "
    "shuttle to the town centre.\n\n"
    "**Dining:** Our restaurant *La Terrazza* serves authentic Amalfi Coast cuisine "
    "with locally sourced ingredients. Breakfast is included with every stay.\n\n"
    "**Pets:** Small dogs are welcome (under 8 kg) with prior arrangement.\n\n"
    "**Room rates** (per night):\n"
    "- Classic — EUR 180\n"
    "- Superior — EUR 280\n"
    "- Deluxe — EUR 420\n"
    "- Suite — EUR 650\n"
    "- Penthouse Suite — EUR 1,200\n\n"
    "Would you like to make a reservation, or is there anything else I can help with?"
)


# ---------------------------------------------------------------------------
# Response templates
# ---------------------------------------------------------------------------

def _welcome():
    return (
        "Buongiorno! Welcome to **Villa Sirene di Positano**, where the Amalfi Coast "
        "meets timeless elegance.\n\n"
        "I am your personal concierge, here to make your experience seamless. "
        "How may I assist you today?\n\n"
        "I can help you with:\n"
        "- **Making a new reservation**\n"
        "- **Viewing** your existing booking\n"
        "- **Modifying** or **cancelling** a reservation\n"
        "- **Answering questions** about our hotel and amenities"
    )


def _room_menu(available_types):
    """Build a formatted room-type menu from a list of dicts with 'type' and 'price'."""
    if not available_types:
        return "I am sorry, but we have no rooms available for those dates. Would you like to try different dates?"

    lines = ["Wonderful! Here are the room types available for your selected dates:\n"]
    for rt in available_types:
        key = rt["type"]
        info = ROOM_INFO.get(key, {})
        label = info.get("label", key.title())
        desc = ROOM_DESCRIPTIONS.get(key, "")
        lines.append(f"- **{label}** — EUR {rt['price']:.0f}/night\n  {desc}\n")
    lines.append("\nWhich type of room would you prefer?")
    return "\n".join(lines)


def _reservation_summary(data):
    """Build a confirmation summary for a pending reservation."""
    room_label = ROOM_INFO.get(data["room_type"], {}).get("label", data["room_type"].title())
    nights = (datetime.strptime(data["check_out"], "%Y-%m-%d") - datetime.strptime(data["check_in"], "%Y-%m-%d")).days
    price = ROOM_INFO.get(data["room_type"], {}).get("price", 0)
    total = price * nights
    return (
        f"Let me confirm the details of your reservation:\n\n"
        f"- **Room:** {room_label}\n"
        f"- **Check-in:** {data['check_in']}\n"
        f"- **Check-out:** {data['check_out']}\n"
        f"- **Duration:** {nights} night{'s' if nights != 1 else ''}\n"
        f"- **Total:** EUR {total:,.0f}\n"
        f"- **Guest:** {data['full_name']}\n"
        f"- **Email:** {_mask_email(data['email'])}\n\n"
        f"Shall I confirm this reservation? (yes / no)"
    )


# ---------------------------------------------------------------------------
# State handlers
# ---------------------------------------------------------------------------

def _handle_idle(msg, data, db_path):
    intent = _detect_intent(msg)

    if intent == "RESERVE":
        return (
            "It would be my pleasure to arrange your stay at Villa Sirene.\n\n"
            "To begin, could you please tell me your desired **check-in date**?",
            RES_DATES_IN, {}
        )
    if intent == "MODIFY":
        return (
            "Of course. To assist you with a modification, I will need to verify your identity first.\n\n"
            "Could you please provide me with the **ID or passport number** used when the reservation was made?",
            MOD_ID, {}
        )
    if intent == "VIEW":
        return (
            "Certainly. To look up your reservation, could you kindly provide me with the "
            "**ID or passport number** associated with the booking?",
            VIEW_ID, {}
        )
    if intent == "CANCEL":
        return (
            "I understand. To proceed with a cancellation, I will need to verify your identity.\n\n"
            "Could you please provide me with your **ID or passport number**?",
            CANCEL_ID, {}
        )
    if intent == "GREETING":
        return (_welcome(), IDLE, {})
    if intent == "INFO":
        return (HOTEL_FAQ, IDLE, {})

    return (
        "Thank you for reaching out. I would be happy to help you.\n\n"
        "Could you let me know what you would like to do? I can assist with:\n"
        "- **Making a new reservation**\n"
        "- **Viewing** your existing booking\n"
        "- **Modifying** or **cancelling** a reservation\n"
        "- **Answering questions** about Villa Sirene",
        IDLE, {}
    )


# ---- Reservation flow ----

def _handle_res_dates_in(msg, data, db_path):
    d = _parse_date(msg)
    if not d:
        return ("I could not quite parse that date. Could you please provide your check-in date in a format such as **15 June 2026** or **2026-06-15**?", RES_DATES_IN, data)
    if d < date.today():
        return ("That date appears to be in the past. Could you please provide a future check-in date?", RES_DATES_IN, data)
    data["check_in"] = d.isoformat()
    return (f"Thank you. And what would be your **check-out date**?", RES_DATES_OUT, data)


def _handle_res_dates_out(msg, data, db_path):
    d = _parse_date(msg)
    if not d:
        return ("I could not parse that date. Could you try a format like **20 June 2026** or **2026-06-20**?", RES_DATES_OUT, data)
    ci = date.fromisoformat(data["check_in"])
    if d <= ci:
        return (f"The check-out date must be after your check-in ({data['check_in']}). Could you provide a later date?", RES_DATES_OUT, data)
    data["check_out"] = d.isoformat()
    available = db.get_available_room_types(db_path, data["check_in"], data["check_out"])
    if not available:
        return (
            "I am sorry, but we have no rooms available for those dates. "
            "Would you like to try different dates? Please provide a new **check-in date**, or type **menu** to return.",
            RES_DATES_IN, {}
        )
    data["_available"] = available
    return (_room_menu(available), RES_ROOM, data)


def _handle_res_room(msg, data, db_path):
    choice = msg.lower().strip()
    available_keys = [rt["type"] for rt in data.get("_available", [])]
    matched = None
    for key in available_keys:
        label = ROOM_INFO.get(key, {}).get("label", "").lower()
        if choice in (key, label) or key in choice or label in choice:
            matched = key
            break
    if not matched:
        options = ", ".join(ROOM_INFO[k]["label"] for k in available_keys)
        return (f"I did not recognise that room type. The available options are: **{options}**. Which would you prefer?", RES_ROOM, data)
    data["room_type"] = matched
    data.pop("_available", None)
    return ("Excellent choice. May I have your **full name** as it appears on your identification, please?", RES_NAME, data)


def _handle_res_name(msg, data, db_path):
    name = msg.strip()
    if len(name) < 2:
        return ("Could you please provide your full name?", RES_NAME, data)
    data["full_name"] = name
    return ("Thank you. And your **ID or passport number**, please?", RES_ID, data)


def _handle_res_id(msg, data, db_path):
    id_num = msg.strip()
    if len(id_num) < 4:
        return ("That does not appear to be a valid ID number. Could you please try again?", RES_ID, data)
    data["id_number"] = id_num
    return ("Thank you. Lastly, could you provide your **email address**? We will send the confirmation there.", RES_EMAIL, data)


def _handle_res_email(msg, data, db_path):
    email = msg.strip()
    if "@" not in email or "." not in email:
        return ("That does not look like a valid email address. Could you please provide a valid email?", RES_EMAIL, data)
    data["email"] = email
    return (_reservation_summary(data), RES_CONFIRM, data)


def _handle_res_confirm(msg, data, db_path):
    m = msg.lower().strip()
    if m in ("yes", "y", "confirm", "si", "oui"):
        result = db.create_reservation(
            db_path, data["full_name"], data["id_number"], data["email"],
            data["room_type"], data["check_in"], data["check_out"]
        )
        if not result:
            return (
                "I am sorry, but that room is no longer available — it may have just been booked. "
                "Would you like to try a different room type or dates? Type **menu** to start over.",
                IDLE, {}
            )
        return (
            f"Your reservation has been confirmed! Here are the details:\n\n"
            f"- **Confirmation code:** {result['code']}\n"
            f"- **Room:** {result['room_number']}\n"
            f"- **Duration:** {result['nights']} night{'s' if result['nights'] != 1 else ''}\n"
            f"- **Total:** EUR {result['total']:,.0f}\n\n"
            f"A confirmation email with all the details has been sent to **{_mask_email(data['email'])}**.\n\n"
            f"We look forward to welcoming you at Villa Sirene. Is there anything else I can help you with?",
            IDLE, {}
        )
    if m in ("no", "n", "cancel"):
        return ("No problem at all. The reservation has not been made. Is there anything else I can help you with?", IDLE, {})
    return ("I just need a simple **yes** or **no** to confirm the reservation.", RES_CONFIRM, data)


# ---- Modification flow ----

def _handle_mod_id(msg, data, db_path):
    id_num = msg.strip()
    if len(id_num) < 4:
        return ("That does not appear to be a valid ID. Could you please try again?", MOD_ID, data)
    res = db.find_reservation_by_id(db_path, id_num)
    if not res:
        return (
            "I could not find an active reservation associated with that ID. "
            "Please double-check the number, or type **menu** to return to the main options.",
            MOD_ID, {}
        )
    data["reservation"] = res
    data["id_number"] = id_num
    room_label = ROOM_INFO.get(res["room_type"], {}).get("label", res["room_type"].title())
    return (
        f"Welcome back, **{res['full_name']}**. I found your reservation:\n\n"
        f"- **Room:** {room_label} (Room {res['room_number']})\n"
        f"- **Check-in:** {res['check_in']}\n"
        f"- **Check-out:** {res['check_out']}\n"
        f"- **Total:** EUR {res['total_price']:,.0f}\n\n"
        f"What would you like to modify?\n"
        f"- **Dates** — change your check-in or check-out\n"
        f"- **Room** — switch to a different room type",
        MOD_SELECT, data
    )


def _handle_mod_select(msg, data, db_path):
    m = msg.lower().strip()
    if "date" in m:
        return ("Certainly. What would be your new **check-in date**?", MOD_DATES_IN, data)
    if "room" in m:
        available = db.get_available_room_types(db_path, data["reservation"]["check_in"], data["reservation"]["check_out"])
        if not available:
            return ("I am sorry, no other rooms are available for your current dates. Would you like to change your **dates** instead, or type **menu** to go back?", MOD_SELECT, data)
        data["_available"] = available
        return (_room_menu(available).replace("your selected dates", "your current dates"), MOD_ROOM, data)
    return ("Could you please specify whether you would like to change the **dates** or the **room** type?", MOD_SELECT, data)


def _handle_mod_dates_in(msg, data, db_path):
    d = _parse_date(msg)
    if not d:
        return ("I could not parse that date. Please try a format like **15 June 2026**.", MOD_DATES_IN, data)
    if d < date.today():
        return ("That date is in the past. Could you please provide a future date?", MOD_DATES_IN, data)
    data["new_check_in"] = d.isoformat()
    return ("And the new **check-out date**?", MOD_DATES_OUT, data)


def _handle_mod_dates_out(msg, data, db_path):
    d = _parse_date(msg)
    if not d:
        return ("I could not parse that date. Please try a format like **20 June 2026**.", MOD_DATES_OUT, data)
    ci = date.fromisoformat(data["new_check_in"])
    if d <= ci:
        return (f"The check-out must be after {data['new_check_in']}. Please provide a later date.", MOD_DATES_OUT, data)
    data["new_check_out"] = d.isoformat()
    nights = (d - ci).days
    price = data["reservation"]["price_per_night"]
    total = price * nights
    data["new_total"] = total
    data["new_nights"] = nights
    return (
        f"Here is the updated summary:\n\n"
        f"- **New check-in:** {data['new_check_in']}\n"
        f"- **New check-out:** {data['new_check_out']}\n"
        f"- **Duration:** {nights} night{'s' if nights != 1 else ''}\n"
        f"- **New total:** EUR {total:,.0f}\n\n"
        f"Shall I confirm this change? (yes / no)",
        MOD_CONFIRM, data
    )


def _handle_mod_room(msg, data, db_path):
    choice = msg.lower().strip()
    available_keys = [rt["type"] for rt in data.get("_available", [])]
    matched = None
    for key in available_keys:
        label = ROOM_INFO.get(key, {}).get("label", "").lower()
        if choice in (key, label) or key in choice or label in choice:
            matched = key
            break
    if not matched:
        options = ", ".join(ROOM_INFO[k]["label"] for k in available_keys)
        return (f"I did not recognise that option. Available types: **{options}**.", MOD_ROOM, data)
    data["new_room_type"] = matched
    data.pop("_available", None)
    room_label = ROOM_INFO[matched]["label"]
    return (f"You would like to switch to a **{room_label}** room. Shall I confirm? (yes / no)", MOD_CONFIRM, data)


def _handle_mod_confirm(msg, data, db_path):
    m = msg.lower().strip()
    if m in ("yes", "y", "confirm", "si", "oui"):
        res = data["reservation"]
        if "new_check_in" in data:
            ok = db.update_reservation_dates(db_path, res["reservation_id"], data["new_check_in"], data["new_check_out"])
            if not ok:
                return ("I am sorry, the room is not available for those new dates. Would you like to try different dates? Type **menu** to go back.", IDLE, {})
        elif "new_room_type" in data:
            result = db.update_reservation_room(db_path, res["reservation_id"], data["new_room_type"])
            if not result:
                return ("I am sorry, that room type is not available for your dates. Would you like another option? Type **menu** to go back.", IDLE, {})
        return (
            f"Your reservation has been updated successfully.\n\n"
            f"An updated confirmation has been sent to **{_mask_email(res['email'])}**.\n\n"
            f"Is there anything else I can help you with?",
            IDLE, {}
        )
    if m in ("no", "n", "cancel"):
        return ("Understood, no changes have been made. Is there anything else I can assist you with?", IDLE, {})
    return ("Could you please confirm with **yes** or **no**?", MOD_CONFIRM, data)


# ---- View flow ----

def _handle_view_id(msg, data, db_path):
    id_num = msg.strip()
    if len(id_num) < 4:
        return ("That does not look like a valid ID. Could you please try again?", VIEW_ID, data)
    res = db.find_reservation_by_id(db_path, id_num)
    if not res:
        return (
            "I could not find an active reservation for that ID. "
            "Please double-check the number, or type **menu** to return.",
            IDLE, {}
        )
    room_label = ROOM_INFO.get(res["room_type"], {}).get("label", res["room_type"].title())
    nights = (datetime.strptime(res["check_out"], "%Y-%m-%d") - datetime.strptime(res["check_in"], "%Y-%m-%d")).days
    return (
        f"Here are your reservation details, **{res['full_name']}**:\n\n"
        f"- **Confirmation code:** {res['confirmation_code']}\n"
        f"- **Room:** {room_label} (Room {res['room_number']})\n"
        f"- **Check-in:** {res['check_in']}\n"
        f"- **Check-out:** {res['check_out']}\n"
        f"- **Duration:** {nights} night{'s' if nights != 1 else ''}\n"
        f"- **Total:** EUR {res['total_price']:,.0f}\n"
        f"- **Status:** {res['status'].title()}\n\n"
        f"Is there anything else I can help you with?",
        IDLE, {}
    )


# ---- Cancel flow ----

def _handle_cancel_id(msg, data, db_path):
    id_num = msg.strip()
    if len(id_num) < 4:
        return ("That does not look like a valid ID. Could you try again?", CANCEL_ID, data)
    res = db.find_reservation_by_id(db_path, id_num)
    if not res:
        return ("I could not find an active reservation for that ID. Type **menu** to return.", IDLE, {})
    data["reservation"] = res
    room_label = ROOM_INFO.get(res["room_type"], {}).get("label", res["room_type"].title())
    return (
        f"I found your reservation, **{res['full_name']}**:\n\n"
        f"- **Room:** {room_label} (Room {res['room_number']})\n"
        f"- **Check-in:** {res['check_in']}\n"
        f"- **Check-out:** {res['check_out']}\n\n"
        f"Are you sure you would like to cancel this reservation? This action cannot be undone. (yes / no)",
        CANCEL_CONFIRM, data
    )


def _handle_cancel_confirm(msg, data, db_path):
    m = msg.lower().strip()
    if m in ("yes", "y", "confirm", "si"):
        res = data["reservation"]
        db.cancel_reservation(db_path, res["reservation_id"])
        return (
            f"Your reservation has been cancelled.\n\n"
            f"A cancellation confirmation has been sent to **{_mask_email(res['email'])}**.\n\n"
            f"We hope to welcome you at Villa Sirene in the future. Is there anything else I can help with?",
            IDLE, {}
        )
    if m in ("no", "n"):
        return ("Your reservation remains unchanged. Is there anything else I can help you with?", IDLE, {})
    return ("Please confirm with **yes** or **no**.", CANCEL_CONFIRM, data)


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

_HANDLERS = {
    IDLE:           _handle_idle,
    RES_DATES_IN:   _handle_res_dates_in,
    RES_DATES_OUT:  _handle_res_dates_out,
    RES_ROOM:       _handle_res_room,
    RES_NAME:       _handle_res_name,
    RES_ID:         _handle_res_id,
    RES_EMAIL:      _handle_res_email,
    RES_CONFIRM:    _handle_res_confirm,
    MOD_ID:         _handle_mod_id,
    MOD_SELECT:     _handle_mod_select,
    MOD_DATES_IN:   _handle_mod_dates_in,
    MOD_DATES_OUT:  _handle_mod_dates_out,
    MOD_ROOM:       _handle_mod_room,
    MOD_CONFIRM:    _handle_mod_confirm,
    VIEW_ID:        _handle_view_id,
    CANCEL_ID:      _handle_cancel_id,
    CANCEL_CONFIRM: _handle_cancel_confirm,
}


def process_message(message, state, data, db_path="hotel.db"):
    """
    Process a user message given the current conversation state.

    Returns:
        (response_text, new_state, new_data)
    """
    msg = message.strip()
    if not msg:
        return ("I did not catch that. Could you please repeat?", state, data)

    if msg.lower() in ("start over", "restart", "menu", "main menu", "go back", "back"):
        return (
            "Of course. " + _welcome().split("\n\n", 1)[1],
            IDLE, {}
        )

    handler = _HANDLERS.get(state, _handle_idle)
    return handler(msg, data, db_path)
