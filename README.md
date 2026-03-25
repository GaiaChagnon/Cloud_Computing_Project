# Villa Sirene di Positano — Concierge Chatbot

A full-stack hotel concierge web application deployed on **AWS EC2** with **Amazon SES** email integration. Guests interact with a conversational chatbot to book, view, modify, and cancel room reservations at a fictional luxury hotel on the Amalfi Coast.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Technology Stack](#technology-stack)
4. [Component Deep Dive](#component-deep-dive)
   - [Flask Application (app.py)](#flask-application-apppy)
   - [Chatbot Engine (chatbot.py)](#chatbot-engine-chatbotpy)
   - [Database Layer (database.py)](#database-layer-databasepy)
   - [Email Service (email_service.py)](#email-service-email_servicepy)
   - [Frontend (templates/ + static/)](#frontend)
5. [Database Schema](#database-schema)
6. [Conversation State Machine](#conversation-state-machine)
7. [API Reference](#api-reference)
8. [Room Catalogue](#room-catalogue)
9. [Email System](#email-system)
10. [Local Development](#local-development)
11. [AWS Deployment](#aws-deployment)
12. [Configuration Reference](#configuration-reference)
13. [Application Notes](#application-notes)
    - [Design Decisions and Trade-offs](#design-decisions-and-trade-offs)
    - [Known Limitations](#known-limitations)
    - [Security Considerations](#security-considerations)
    - [Troubleshooting](#troubleshooting)
    - [Performance Profile](#performance-profile)
14. [Sample Data](#sample-data)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (Client)                         │
│  index.html  ·  script.js  ·  style.css                     │
│  Three views: Chat / Rooms Showcase / Booking Lookup        │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP (JSON)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   app.py — Flask (Gunicorn)                 │
│  /api/chat  ·  /api/rooms  ·  /api/lookup  ·  /api/reset    │
│  In-memory session store (cookie-based sid)                 │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
           ▼                              ▼
┌──────────────────────┐    ┌──────────────────────────────────┐
│   chatbot.py         │    │   email_service.py               │
│   State machine      │    │   SES (boto3) → SMTP → no-op     │
│   Intent detection   │    │   HTML confirmation emails       │
│   Room info / FAQ    │    └──────────────────────────────────┘
└──────────┬───────────┘                  ▲
           │                             │
           ▼                             │ app.py triggers emails
┌──────────────────────┐                 │ on booking events
│   database.py        │                 │
│   SQLite (hotel.db)  │─────────────────┘
│   rooms · guests ·   │
│   reservations       │
└──────────────────────┘
```

**Hosting:** Single AWS EC2 instance (Amazon Linux 2023) running Gunicorn on port 80.
**Email:** Amazon SES via IAM role attached to the EC2 instance, with SMTP fallback.

---

## Project Structure

```
Cloud_Computing_Project/
├── app.py                 # Flask web application — routes, session management, email dispatch
├── chatbot.py             # Conversation engine — state machine, intent detection, responses
├── database.py            # SQLite database — schema, CRUD operations, room availability
├── email_service.py       # Email delivery — SES + SMTP transports, HTML email templates
├── deploy.sh              # One-command EC2 deployment script
├── setup_ses.py           # CLI utility for SES verification and testing
├── requirements.txt       # Python dependencies with pinned versions
├── .env.example           # Environment variable template for email configuration
├── .gitignore             # Excludes hotel.db, .env, __pycache__, venv
├── templates/
│   └── index.html         # Single-page Jinja2 template — chat, rooms, lookup views
└── static/
    ├── script.js          # Frontend logic — chat I/O, view switching, room loading, modals
    └── style.css          # Design system — navy/gold/cream palette, responsive layout
```

---

## Technology Stack

| Layer       | Technology                  | Version    | Purpose                                          |
|-------------|-----------------------------|------------|--------------------------------------------------|
| Runtime     | Python 3                    | 3.9+       | Application language                             |
| Web         | Flask                       | 3.1.0      | HTTP routing, Jinja2 templating, JSON API        |
| WSGI        | Gunicorn                    | 23.0.0     | Production-grade WSGI server (1 worker, port 80) |
| Database    | SQLite                      | built-in   | Embedded relational database (`hotel.db`)        |
| Date parsing| python-dateutil             | 2.9.0      | Flexible human-readable date parsing             |
| AWS SDK     | boto3                       | >= 1.35.0  | Amazon SES email API                             |
| Hosting     | AWS EC2                     | —          | Amazon Linux 2023 instance                       |
| Email       | Amazon SES                  | —          | Transactional emails (confirmation/mod/cancel)   |
| Frontend    | Vanilla JS + CSS            | —          | No frameworks; single-page app with three views  |
| Fonts       | Inter + Cormorant Garamond  | —          | Google Fonts — UI text + display headings        |

All dependencies are listed in `requirements.txt`. No frontend build step is required.

---

## Component Deep Dive

### Flask Application (`app.py`)

The central orchestrator. Serves the UI, manages sessions, routes chat messages through the chatbot engine, and triggers email delivery on booking events.

**Session management:** In-memory dictionary keyed by a `sid` cookie (UUID hex). Each session stores the current conversation `state` and accumulated `data` (dates, room type, guest info). Sessions are not persisted across restarts — this is acceptable for a single-instance demo.

**Email event detection:** After every chat response, `_handle_email_events()` inspects the response text for trigger phrases (`"has been confirmed"`, `"has been updated"`, `"has been cancelled"`) combined with the previous conversation state to determine whether to dispatch an email. This decouples email logic from the chatbot engine itself.

**Key functions:**

| Function               | Purpose                                                                 |
|------------------------|-------------------------------------------------------------------------|
| `_get_session(req)`    | Retrieve or create session from cookie; returns `(sid, session_dict)`   |
| `_mask_email(email)`   | Mask email for display: `j***n@gmail.com`                               |
| `chat()`               | POST `/api/chat` — process message, update session, trigger emails      |
| `_handle_email_events()`| Detect booking events and call `email_service.send_*()` functions      |
| `lookup()`             | POST `/api/lookup` — find reservation by confirmation code or ID        |
| `rooms()`              | GET `/api/rooms` — return room type catalogue from database             |

### Chatbot Engine (`chatbot.py`)

A deterministic state machine that drives the entire conversation flow. No LLM or NLP library is used — intent detection is keyword-based, which makes the system predictable, testable, and free of API dependencies.

**Design decisions:**
- **Keyword intent detection** over ML models — ensures deterministic behaviour, zero external API calls, and sub-millisecond response times.
- **State-per-step** rather than free-form — prevents ambiguous conversation branches and enforces required data collection (dates, name, ID, email) in order.
- **Privacy by design** — ID numbers and emails are masked in all bot responses using `_mask_email()` and `_mask_id()`.

**Intent categories:**

| Intent    | Trigger keywords                                                    |
|-----------|---------------------------------------------------------------------|
| RESERVE   | book, reserve, reservation, new booking, need a room, like to stay  |
| MODIFY    | modify, change, update, edit, modification                          |
| VIEW      | view, check, look up, find, show, status, my reservation            |
| CANCEL    | cancel                                                              |
| GREETING  | hello, hi, hey, buongiorno, ciao, good morning/afternoon/evening    |
| INFO      | amenities, restaurant, pool, spa, price, rate, breakfast, parking   |

**Global escape:** At any point, typing `menu`, `start over`, `restart`, `go back`, or `back` returns to IDLE.

### Database Layer (`database.py`)

SQLite-based persistence with three tables. The database file (`hotel.db`) is created and seeded automatically on first run via `init_db()`.

**Key functions:**

| Function                      | Purpose                                                         |
|-------------------------------|-----------------------------------------------------------------|
| `init_db(db_path)`            | Create tables + seed rooms and sample data if empty             |
| `get_available_room_types()`  | Room types with at least one free room for a date range         |
| `find_available_room()`       | First available `room_id` of a given type for dates             |
| `create_reservation()`        | Insert guest (or update) + reservation; returns code + details  |
| `find_reservation_by_id()`    | Look up latest confirmed reservation by ID/passport number      |
| `find_reservation_by_code()`  | Look up by `VS-XXXXXX` confirmation code                        |
| `update_reservation_dates()`  | Change check-in/check-out with conflict check                   |
| `update_reservation_room()`   | Switch room type with availability check                        |
| `cancel_reservation()`        | Set reservation status to `cancelled`                           |
| `get_room_type_summary()`     | Aggregate room types for the showcase page                      |

**Confirmation codes:** Format `VS-XXXXXX` (6 uppercase alphanumeric characters), generated with collision checking.

**Concurrency:** SQLite with `PRAGMA foreign_keys = ON`. Single-worker Gunicorn avoids write contention.

### Email Service (`email_service.py`)

Sends styled HTML transactional emails with a three-tier transport strategy:

1. **Amazon SES** (preferred) — uses IAM role credentials via `boto3`. No secrets in code or `.env`.
2. **SMTP relay** (fallback) — e.g. Gmail with an App Password. Configured via environment variables.
3. **Graceful no-op** — if neither is available, logs a warning and skips the send. The app continues to function.

**Transport selection is automatic** — the service probes SES on first use (`get_send_quota()`), caches the result, and falls back transparently.

**Email types:**

| Function               | Trigger                          | Subject line format                             |
|------------------------|----------------------------------|-------------------------------------------------|
| `send_confirmation()`  | New reservation confirmed        | `Booking Confirmation VS-XXXXXX — Villa Sirene` |
| `send_modification()`  | Reservation dates/room changed   | `Booking Updated VS-XXXXXX — Villa Sirene`      |
| `send_cancellation()`  | Reservation cancelled            | `Booking Cancelled VS-XXXXXX — Villa Sirene`    |

**HTML template:** Table-based layout for maximum email client compatibility (Outlook, Gmail, Apple Mail). Navy header with gold VS monogram, detail grid, and branded footer.

### Frontend

Single-page application with three views, built with vanilla JavaScript and CSS. No build tools or frameworks.

**Views:**

| View    | Tab label    | Description                                                    |
|---------|-------------|----------------------------------------------------------------|
| Chat    | Concierge   | Conversational interface with quick-action buttons and typing indicator |
| Rooms   | Our Rooms   | Card grid fetched from `/api/rooms` with Unsplash images       |
| Lookup  | My Booking  | Form to search by confirmation code or ID; displays result card |

**Design system:**
- **Palette:** Navy (`#0c2340`), Gold (`#c9a84c`), Cream (`#faf8f4`)
- **Typography:** Inter (UI text), Cormorant Garamond (display headings)
- **Responsive:** Breakpoint at 640px; single-column layout on mobile

**Features:**
- Markdown-lite rendering in chat (bold, italic, bullet lists)
- Typing indicator with animated dots
- Email confirmation modal (preview of the HTML email)
- Toast notifications for email events
- Auto-resizing textarea (max 120px)
- `Esc` key closes modals; `Enter` sends messages; `Shift+Enter` for newlines

---

## Database Schema

```sql
CREATE TABLE rooms (
    room_id         INTEGER PRIMARY KEY,
    room_number     TEXT    UNIQUE NOT NULL,     -- e.g. "101", "501"
    room_type       TEXT    NOT NULL,            -- classic|superior|deluxe|suite|penthouse
    floor           INTEGER NOT NULL,            -- 1-5
    price_per_night REAL    NOT NULL,            -- EUR
    description     TEXT
);

CREATE TABLE guests (
    guest_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name  TEXT    NOT NULL,
    id_number  TEXT    NOT NULL,                 -- passport or national ID
    email      TEXT    NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE reservations (
    reservation_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    confirmation_code TEXT    UNIQUE NOT NULL,   -- VS-XXXXXX
    guest_id          INTEGER NOT NULL REFERENCES guests(guest_id),
    room_id           INTEGER NOT NULL REFERENCES rooms(room_id),
    check_in          DATE    NOT NULL,
    check_out         DATE    NOT NULL,
    status            TEXT    DEFAULT 'confirmed',  -- confirmed|cancelled
    total_price       REAL    NOT NULL,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Relationships:**
- `reservations.guest_id` → `guests.guest_id` (many-to-one)
- `reservations.room_id` → `rooms.room_id` (many-to-one)
- Foreign keys enforced via `PRAGMA foreign_keys = ON`

---

## Conversation State Machine

The chatbot uses 17 distinct states across four conversation flows. Every state has a single handler function. State transitions are deterministic.

### Reservation Flow (new booking)

```
IDLE
  ↓  (user says "book a room")
RES_DATES_IN    → collect check-in date
  ↓
RES_DATES_OUT   → collect check-out date, check availability
  ↓
RES_ROOM        → display available room types, collect choice
  ↓
RES_NAME        → collect full name
  ↓
RES_ID          → collect ID / passport number
  ↓
RES_EMAIL       → collect email address
  ↓
RES_CONFIRM     → show summary, ask yes/no
  ↓  (yes)
IDLE            → reservation created, confirmation code returned, email sent
```

### Modification Flow

```
IDLE
  ↓  (user says "modify my booking")
MOD_ID          → collect ID / passport number, look up reservation
  ↓
MOD_SELECT      → ask: change dates or room type?
  ↓
MOD_DATES_IN → MOD_DATES_OUT → MOD_CONFIRM    (date change path)
MOD_ROOM → MOD_CONFIRM                         (room change path)
  ↓  (yes)
IDLE            → reservation updated, email sent
```

### View Flow

```
IDLE → VIEW_ID → display reservation details → IDLE
```

### Cancel Flow

```
IDLE → CANCEL_ID → CANCEL_CONFIRM → IDLE (reservation cancelled, email sent)
```

---

## API Reference

### `POST /api/chat`

Process a chat message and return the bot's response.

**Request:**
```json
{ "message": "I would like to book a room" }
```

**Response:**
```json
{
    "response": "It would be my pleasure to arrange your stay...",
    "event": "booking_confirmed",
    "confirmation": {
        "code": "VS-A1B2C3",
        "guest_name": "Marco Bellini",
        "room_type": "Deluxe",
        "room_number": "203",
        "check_in": "2026-06-15",
        "check_out": "2026-06-20",
        "nights": 5,
        "total_price": 2100,
        "email": "m***o@email.it"
    }
}
```

The `event` and `confirmation` fields are only present when a booking event occurs. Possible events: `booking_confirmed`, `booking_modified`, `booking_cancelled`.

### `POST /api/lookup`

Look up a reservation by confirmation code or ID number.

**Request (by code):**
```json
{ "confirmation_code": "VS-A1B2C3" }
```

**Request (by ID):**
```json
{ "id_number": "IT48291056" }
```

**Response:**
```json
{
    "found": true,
    "reservation": {
        "confirmation_code": "VS-A1B2C3",
        "guest_name": "Marco Bellini",
        "room_type": "Deluxe",
        "room_number": "203",
        "check_in": "2026-06-15",
        "check_out": "2026-06-20",
        "nights": 5,
        "total_price": 2100,
        "status": "confirmed",
        "email": "m***o@email.it"
    }
}
```

### `GET /api/rooms`

Return the room type catalogue (one entry per type, aggregated).

**Response:**
```json
[
    {
        "type": "classic",
        "label": "Classic",
        "price": 180,
        "description": "Charming room with Mediterranean décor...",
        "total_rooms": 3,
        "floors": "1-2"
    }
]
```

### `POST /api/reset`

Reset the current session to IDLE state with empty data.

**Response:**
```json
{ "ok": true }
```

### `GET /health`

Health check endpoint.

**Response:**
```json
{ "status": "ok", "service": "villa-sirene-concierge" }
```

---

## Room Catalogue

The hotel has **12 rooms** across **5 floors** and **5 room types**:

| Type       | Label            | Price/Night (EUR) | Rooms | Floors | Description                                                                      |
|------------|------------------|--------------------|-------|--------|----------------------------------------------------------------------------------|
| classic    | Classic          | 180                | 3     | 1-2    | Mediterranean decor, terracotta floors, balcony overlooking the village           |
| superior   | Superior         | 280                | 3     | 1-3    | Hand-painted tiles, antique furnishings, partial sea views                        |
| deluxe     | Deluxe           | 420                | 4     | 2-4    | Panoramic sea views, marble bathroom, sunset terrace                             |
| suite      | Suite            | 650                | 1     | 4      | Separate living area, premium sea views, soaking tub, garden terrace             |
| penthouse  | Penthouse Suite  | 1,200              | 1     | 5      | Wraparound terrace, 360-degree Amalfi Coast views, private jacuzzi              |

**Room number layout:**

| Room   | Type       | Floor |
|--------|------------|-------|
| 101    | Classic    | 1     |
| 102    | Classic    | 1     |
| 103    | Superior   | 1     |
| 201    | Classic    | 2     |
| 202    | Superior   | 2     |
| 203    | Deluxe     | 2     |
| 301    | Superior   | 3     |
| 302    | Deluxe     | 3     |
| 303    | Deluxe     | 3     |
| 401    | Suite      | 4     |
| 402    | Deluxe     | 4     |
| 501    | Penthouse  | 5     |

---

## Email System

### Transport Priority

```
1. Amazon SES (boto3)  →  IAM role on EC2, no credentials needed
         ↓ (unavailable)
2. SMTP relay          →  Gmail App Password or any SMTP server
         ↓ (unavailable)
3. No-op               →  Log warning, app continues normally
```

### SES Setup (on EC2)

1. Attach an IAM role with `AmazonSESFullAccess` to the EC2 instance.
2. Verify sender and recipient emails (required in SES sandbox mode):
   ```bash
   python3 setup_ses.py verify your@email.com
   ```
3. Check status:
   ```bash
   python3 setup_ses.py status
   ```
4. Send a test email:
   ```bash
   python3 setup_ses.py test sender@email.com recipient@email.com
   ```

### SES Sandbox Limitations

In sandbox mode (default for new AWS accounts):
- Maximum 200 emails per 24 hours
- Maximum 1 email per second
- Both sender and recipient must be verified
- Request production access via AWS Console to lift these limits

### SMTP Fallback

Create a `.env` file from the template:
```bash
cp .env.example .env
```

For Gmail:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-16-char-app-password
```

Generate a Gmail App Password at https://myaccount.google.com/apppasswords (requires 2FA enabled).

---

## Local Development

### Prerequisites

- Python 3.9 or later
- pip

### Setup

```bash
git clone <repository-url>
cd Cloud_Computing_Project

pip install -r requirements.txt

python app.py
```

The server starts on `http://localhost:5000`. The SQLite database (`hotel.db`) is created and seeded automatically on first run.

### Email (optional)

Without any email configuration, the app functions normally — emails are silently skipped with a log message. To enable email locally, copy `.env.example` to `.env` and configure SMTP credentials.

---

## AWS Deployment

### Prerequisites

- An EC2 instance running Amazon Linux 2023
- Security group allowing inbound HTTP (port 80)
- IAM role with `AmazonSESFullAccess` attached to the instance (for email)

### Deploy

SSH into the EC2 instance, clone the repo, and run:

```bash
git clone <repository-url>
cd Cloud_Computing_Project

bash deploy.sh
```

**What `deploy.sh` does:**
1. Updates system packages (`yum`/`dnf`)
2. Installs Python 3, pip, and git
3. Installs Python dependencies system-wide
4. Initialises the SQLite database with seed data
5. Stops any existing Gunicorn process
6. Starts Gunicorn as a daemon on port 80 (1 worker)
7. Verifies the health check returns HTTP 200
8. Prints the public URL and log file locations

### Logs

| Log                               | Content                    |
|-----------------------------------|----------------------------|
| `/tmp/villa_sirene_access.log`    | HTTP request log           |
| `/tmp/villa_sirene_error.log`     | Application errors         |

### Process Management

```bash
# Check if running
curl http://localhost/health

# View logs
tail -f /tmp/villa_sirene_error.log

# Restart
sudo pkill gunicorn && bash deploy.sh

# Stop
sudo pkill gunicorn
```

---

## Configuration Reference

### Environment Variables

| Variable      | Default          | Description                                       |
|---------------|------------------|---------------------------------------------------|
| `SES_REGION`  | `eu-central-1`   | AWS region for the SES API                        |
| `SES_SENDER`  | (auto-detected)  | Verified sender email; auto-detected from SES if unset |
| `SMTP_HOST`   | `smtp.gmail.com` | SMTP server hostname                              |
| `SMTP_PORT`   | `587`            | SMTP server port (TLS)                            |
| `SMTP_USER`   | (empty)          | SMTP login username                               |
| `SMTP_PASS`   | (empty)          | SMTP login password / app password                |

Environment variables can be set in a `.env` file in the project root (see `.env.example`) or as actual environment variables.

### Runtime Defaults

| Parameter          | Value   | Location                     |
|--------------------|---------|------------------------------|
| Flask host         | 0.0.0.0 | `app.py` line 218           |
| Flask port (dev)   | 5000    | `app.py` line 218           |
| Gunicorn port      | 80      | `deploy.sh`                 |
| Gunicorn workers   | 1       | `deploy.sh`                 |
| SQLite DB path     | `hotel.db` | `app.py` line 25         |
| Session storage    | in-memory | `app.py` (dict `sessions`) |

---

## Application Notes

### Design Decisions and Trade-offs

| Decision | Rationale |
|----------|-----------|
| **Keyword-based intent detection** (no NLP/LLM) | Deterministic, testable, zero external API calls, sub-millisecond response times. Trades conversational flexibility for predictability — acceptable for a structured reservation flow. |
| **State-machine conversation model** | Each step collects exactly one piece of data, preventing ambiguous branches. The 17-state design covers four complete workflows (book, view, modify, cancel) with clear entry/exit points. |
| **SQLite over a managed database** | Single-file embedded database with zero configuration. Ideal for a single-instance demo. For production multi-instance deployment, migrate to PostgreSQL or Amazon RDS. |
| **Single Gunicorn worker** | SQLite does not handle concurrent writes well. A single worker avoids write contention entirely. Scale by switching to PostgreSQL + multiple workers. |
| **In-memory session store** | Sessions are stored in a Python `dict` keyed by a UUID cookie. Fast and simple, but sessions are lost on restart. For persistence, swap to Redis or DynamoDB-backed sessions. |
| **Three-tier email transport** | SES (IAM role) > SMTP (credentials) > no-op. The app never fails due to email misconfiguration — it degrades gracefully and logs the skip. |
| **Vanilla JS frontend** | No build step, no framework dependencies, no version churn. The entire SPA (chat, rooms, lookup) loads in a single HTML file with two static assets. |
| **Privacy masking by default** | Guest ID numbers and emails are never echoed in full by the chatbot or the API. Masking happens in both `chatbot.py` and `app.py` independently. |

### Known Limitations

| Area | Limitation | Mitigation / Path Forward |
|------|-----------|--------------------------|
| **Concurrency** | Single Gunicorn worker; SQLite write lock under concurrent requests | Switch to PostgreSQL + increase worker count for production loads |
| **Session persistence** | In-memory sessions lost on process restart | Plug in Redis, a database-backed store, or signed JWT tokens |
| **Intent detection** | Keyword matching cannot handle misspellings, synonyms, or multi-intent messages | Integrate a lightweight NLU layer (e.g. Rasa, spaCy matcher) if broader language coverage is needed |
| **Date parsing** | `python-dateutil` handles most formats but may misinterpret ambiguous inputs like "03/04" (March 4 vs. April 3) | `dayfirst=True` is set to prefer European format; document this for users |
| **Email in SES sandbox** | Sandbox mode limits to 200 emails/day and requires verified sender + recipient | Request production access via the AWS Console once the domain is validated |
| **No HTTPS termination** | Gunicorn serves plain HTTP on port 80 | Place behind an ALB with an ACM certificate, or use Caddy/Nginx as a TLS-terminating reverse proxy |
| **No rate limiting** | API endpoints are unprotected against abuse | Add Flask-Limiter or an API Gateway throttle in front of the EC2 instance |
| **Static room images** | Room showcase uses Unsplash placeholder images loaded client-side | Replace with actual hotel photography served from S3/CloudFront |

### Security Considerations

- **No secrets in code.** SES uses the EC2 IAM role (no access keys). SMTP credentials live in `.env` which is `.gitignore`d.
- **Cookie security.** The `sid` cookie is `HttpOnly` and `SameSite=Lax`. For HTTPS deployments, add `Secure=True` in `app.py`.
- **Input validation.** All user inputs (dates, names, emails, IDs) are validated at the chatbot layer before reaching the database. SQL parameters are always bound (no string interpolation).
- **Foreign key enforcement.** `PRAGMA foreign_keys = ON` is set on every connection to prevent orphaned records.
- **Email masking.** Both the chatbot responses and the REST API mask guest emails (`j***n@gmail.com`) and ID numbers (`***1056`) to prevent accidental data exposure in logs or screenshots.
- **No admin interface.** There is no route that exposes the full guest or reservation list. Lookup requires a confirmation code or ID number.

### Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `gunicorn: command not found` | pip installed to user site, not system-wide | Run `sudo pip3 install gunicorn` or adjust `PATH` |
| Database is empty after restart | `hotel.db` was deleted or the working directory changed | Re-run `python3 -c "from database import init_db; init_db('hotel.db')"` |
| Emails not sending, no errors | Neither SES nor SMTP is configured — the no-op fallback is active | Check `[Email]` log lines in `/tmp/villa_sirene_error.log`; configure SES or SMTP |
| SES returns `MessageRejected` | Sender or recipient not verified (sandbox mode) | Run `python3 setup_ses.py verify EMAIL` for both addresses |
| Chat returns generic fallback | User message did not match any keyword intent | Check the intent keyword lists in `chatbot.py _detect_intent()`; add synonyms if needed |
| Port 80 already in use | Another process (httpd, nginx) is bound to port 80 | `sudo lsof -i :80` to identify, then stop the conflicting process |
| `ModuleNotFoundError: flask` | Dependencies not installed in the active Python environment | `pip install -r requirements.txt` or re-run `deploy.sh` |
| Session lost mid-conversation | Server restarted (sessions are in-memory) | Expected behaviour; user simply starts a new conversation |

### Performance Profile

| Metric | Value | Notes |
|--------|-------|-------|
| Cold start (first request) | ~200 ms | Database init + room seeding on first `init_db()` call |
| Chat response latency | < 5 ms | Keyword matching + single SQLite query; no network calls |
| Email dispatch (SES) | 100-300 ms | Network round-trip to SES API; non-blocking to the user (response returns immediately) |
| Memory footprint | ~30-50 MB | Flask + Gunicorn + SQLite; scales with session count |
| Database file size | ~40 KB | 12 rooms, 3 sample guests; grows linearly with reservations |
| Static asset size | ~45 KB total | `style.css` + `script.js` + `index.html`; no framework bundle |

---

## Sample Data

The database is seeded with three sample guests and reservations for demo and testing purposes:

| Guest             | ID Number    | Email                      | Room  | Check-in    | Check-out   |
|-------------------|-------------|----------------------------|-------|-------------|-------------|
| Marco Bellini     | IT48291056  | marco.bellini@email.it     | 101 (Classic)   | 2026-04-10 | 2026-04-15 |
| Sophie Laurent    | FR72839104  | sophie.laurent@email.fr    | 302 (Deluxe)    | 2026-04-12 | 2026-04-18 |
| William Chen      | US93847261  | william.chen@email.com     | 401 (Suite)     | 2026-05-01 | 2026-05-05 |

Use these ID numbers in the chatbot to test the view, modify, and cancel flows.
