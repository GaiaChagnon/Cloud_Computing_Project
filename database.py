"""
Hotel reservation database for Villa Sirene di Positano.

Schema: rooms, guests, reservations.
Initialises with 12 rooms across 5 floors and sample bookings for testing.
"""

import sqlite3
import random
import string
from datetime import datetime

DB_PATH = "hotel.db"


def get_db(db_path=None):
    """Return a connection with row-factory enabled."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    """Create tables, seed rooms and sample reservations."""
    conn = get_db(db_path)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS rooms (
            room_id     INTEGER PRIMARY KEY,
            room_number TEXT    UNIQUE NOT NULL,
            room_type   TEXT    NOT NULL,
            floor       INTEGER NOT NULL,
            price_per_night REAL NOT NULL,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS guests (
            guest_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name  TEXT    NOT NULL,
            id_number  TEXT    NOT NULL,
            email      TEXT    NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            confirmation_code TEXT    UNIQUE NOT NULL,
            guest_id          INTEGER NOT NULL,
            room_id           INTEGER NOT NULL,
            check_in          DATE    NOT NULL,
            check_out         DATE    NOT NULL,
            status            TEXT    DEFAULT 'confirmed',
            total_price       REAL    NOT NULL,
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guest_id) REFERENCES guests(guest_id),
            FOREIGN KEY (room_id)  REFERENCES rooms(room_id)
        );
    """)

    if cur.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
        _seed_rooms(cur)
        _seed_sample_data(cur)

    conn.commit()
    conn.close()


def _seed_rooms(cur):
    """Populate 12 rooms across 5 floors."""
    rooms = [
        ("101", "classic",   1,  180, "Charming room with Mediterranean décor, terracotta floors, and a balcony overlooking the village."),
        ("102", "classic",   1,  180, "Charming room with Mediterranean décor, terracotta floors, and a balcony overlooking the village."),
        ("103", "superior",  1,  280, "Spacious retreat with hand-painted tiles, antique furnishings, and partial sea views."),
        ("201", "classic",   2,  180, "Charming room with Mediterranean décor, terracotta floors, and a balcony overlooking the village."),
        ("202", "superior",  2,  280, "Spacious retreat with hand-painted tiles, antique furnishings, and partial sea views."),
        ("203", "deluxe",    2,  420, "Elegant room with panoramic sea views, marble bathroom, and sunset terrace."),
        ("301", "superior",  3,  280, "Spacious retreat with hand-painted tiles, antique furnishings, and partial sea views."),
        ("302", "deluxe",    3,  420, "Elegant room with panoramic sea views, marble bathroom, and sunset terrace."),
        ("303", "deluxe",    3,  420, "Elegant room with panoramic sea views, marble bathroom, and sunset terrace."),
        ("401", "suite",     4,  650, "Luxurious suite with separate living area, premium sea views, soaking tub, and garden terrace."),
        ("402", "deluxe",    4,  420, "Elegant room with panoramic sea views, marble bathroom, and sunset terrace."),
        ("501", "penthouse", 5, 1200, "Exclusive penthouse with wraparound terrace, 360° Amalfi Coast views, and private jacuzzi."),
    ]
    for r in rooms:
        cur.execute(
            "INSERT INTO rooms (room_number, room_type, floor, price_per_night, description) VALUES (?,?,?,?,?)", r
        )


def _seed_sample_data(cur):
    """Insert sample guests and reservations for demo purposes."""
    guests = [
        ("Marco Bellini",  "IT48291056", "marco.bellini@email.it"),
        ("Sophie Laurent",  "FR72839104", "sophie.laurent@email.fr"),
        ("William Chen",    "US93847261", "william.chen@email.com"),
    ]
    for g in guests:
        cur.execute("INSERT INTO guests (full_name, id_number, email) VALUES (?,?,?)", g)

    sample_reservations = [
        (1, 1,  "2026-04-10", "2026-04-15"),
        (2, 8,  "2026-04-12", "2026-04-18"),
        (3, 10, "2026-05-01", "2026-05-05"),
    ]
    for guest_id, room_id, ci, co in sample_reservations:
        code = _generate_confirmation_code(cur)
        price = cur.execute("SELECT price_per_night FROM rooms WHERE room_id=?", (room_id,)).fetchone()[0]
        nights = (datetime.strptime(co, "%Y-%m-%d") - datetime.strptime(ci, "%Y-%m-%d")).days
        cur.execute(
            "INSERT INTO reservations (confirmation_code, guest_id, room_id, check_in, check_out, status, total_price) "
            "VALUES (?,?,?,?,?,?,?)",
            (code, guest_id, room_id, ci, co, "confirmed", price * nights),
        )


def _generate_confirmation_code(cur):
    """Generate a unique VS-XXXXXX confirmation code."""
    while True:
        code = "VS-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if cur.execute("SELECT 1 FROM reservations WHERE confirmation_code=?", (code,)).fetchone() is None:
            return code


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def find_available_room(db_path, room_type, check_in, check_out):
    """Return the first available room_id of the given type for the date range, or None."""
    conn = get_db(db_path)
    row = conn.execute(
        """
        SELECT r.room_id FROM rooms r
        WHERE r.room_type = ?
          AND r.room_id NOT IN (
              SELECT res.room_id FROM reservations res
              WHERE res.status = 'confirmed'
                AND res.check_in < ? AND res.check_out > ?
          )
        ORDER BY r.floor ASC
        LIMIT 1
        """,
        (room_type, check_out, check_in),
    ).fetchone()
    conn.close()
    return row["room_id"] if row else None


def get_available_room_types(db_path, check_in, check_out):
    """Return a list of room types that have at least one room free for the date range."""
    conn = get_db(db_path)
    rows = conn.execute(
        """
        SELECT DISTINCT r.room_type, r.price_per_night FROM rooms r
        WHERE r.room_id NOT IN (
            SELECT res.room_id FROM reservations res
            WHERE res.status = 'confirmed'
              AND res.check_in < ? AND res.check_out > ?
        )
        ORDER BY r.price_per_night ASC
        """,
        (check_out, check_in),
    ).fetchall()
    conn.close()
    return [{"type": row["room_type"], "price": row["price_per_night"]} for row in rows]


def find_reservation_by_id(db_path, id_number):
    """Look up the latest confirmed reservation for a guest by their ID document number."""
    conn = get_db(db_path)
    row = conn.execute(
        """
        SELECT res.*, g.full_name, g.email, g.id_number, g.guest_id,
               rm.room_type, rm.room_number, rm.price_per_night
        FROM reservations res
        JOIN guests g  ON g.guest_id  = res.guest_id
        JOIN rooms  rm ON rm.room_id  = res.room_id
        WHERE g.id_number = ? AND res.status = 'confirmed'
        ORDER BY res.check_in DESC
        LIMIT 1
        """,
        (id_number,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_reservation(db_path, full_name, id_number, email, room_type, check_in, check_out):
    """Create a new reservation. Returns (confirmation_code, room_number, total_price) or None."""
    conn = get_db(db_path)
    cur = conn.cursor()

    room_id_row = conn.execute(
        """
        SELECT r.room_id, r.room_number, r.price_per_night FROM rooms r
        WHERE r.room_type = ?
          AND r.room_id NOT IN (
              SELECT res.room_id FROM reservations res
              WHERE res.status = 'confirmed'
                AND res.check_in < ? AND res.check_out > ?
          )
        ORDER BY r.floor ASC LIMIT 1
        """,
        (room_type, check_out, check_in),
    ).fetchone()

    if not room_id_row:
        conn.close()
        return None

    existing_guest = conn.execute(
        "SELECT guest_id FROM guests WHERE id_number = ?", (id_number,)
    ).fetchone()

    if existing_guest:
        guest_id = existing_guest["guest_id"]
        cur.execute("UPDATE guests SET full_name=?, email=? WHERE guest_id=?", (full_name, email, guest_id))
    else:
        cur.execute("INSERT INTO guests (full_name, id_number, email) VALUES (?,?,?)", (full_name, id_number, email))
        guest_id = cur.lastrowid

    nights = (datetime.strptime(check_out, "%Y-%m-%d") - datetime.strptime(check_in, "%Y-%m-%d")).days
    total = room_id_row["price_per_night"] * nights
    code = _generate_confirmation_code(cur)

    cur.execute(
        "INSERT INTO reservations (confirmation_code, guest_id, room_id, check_in, check_out, status, total_price) "
        "VALUES (?,?,?,?,?,?,?)",
        (code, guest_id, room_id_row["room_id"], check_in, check_out, "confirmed", total),
    )
    conn.commit()
    conn.close()
    return {"code": code, "room_number": room_id_row["room_number"], "total": total, "nights": nights}


def update_reservation_dates(db_path, reservation_id, new_check_in, new_check_out):
    """Change the dates of an existing reservation. Returns True on success."""
    conn = get_db(db_path)
    cur = conn.cursor()

    res = conn.execute(
        "SELECT room_id FROM reservations WHERE reservation_id=? AND status='confirmed'",
        (reservation_id,),
    ).fetchone()
    if not res:
        conn.close()
        return False

    conflict = conn.execute(
        """
        SELECT 1 FROM reservations
        WHERE room_id = ? AND reservation_id != ? AND status = 'confirmed'
          AND check_in < ? AND check_out > ?
        """,
        (res["room_id"], reservation_id, new_check_out, new_check_in),
    ).fetchone()
    if conflict:
        conn.close()
        return False

    price = conn.execute("SELECT price_per_night FROM rooms WHERE room_id=?", (res["room_id"],)).fetchone()["price_per_night"]
    nights = (datetime.strptime(new_check_out, "%Y-%m-%d") - datetime.strptime(new_check_in, "%Y-%m-%d")).days
    cur.execute(
        "UPDATE reservations SET check_in=?, check_out=?, total_price=? WHERE reservation_id=?",
        (new_check_in, new_check_out, price * nights, reservation_id),
    )
    conn.commit()
    conn.close()
    return True


def update_reservation_room(db_path, reservation_id, new_room_type):
    """Change the room type of an existing reservation. Returns new room info or None."""
    conn = get_db(db_path)
    cur = conn.cursor()

    res = conn.execute(
        "SELECT check_in, check_out FROM reservations WHERE reservation_id=? AND status='confirmed'",
        (reservation_id,),
    ).fetchone()
    if not res:
        conn.close()
        return None

    new_room = conn.execute(
        """
        SELECT r.room_id, r.room_number, r.price_per_night FROM rooms r
        WHERE r.room_type = ?
          AND r.room_id NOT IN (
              SELECT res2.room_id FROM reservations res2
              WHERE res2.status = 'confirmed' AND res2.reservation_id != ?
                AND res2.check_in < ? AND res2.check_out > ?
          )
        ORDER BY r.floor ASC LIMIT 1
        """,
        (new_room_type, reservation_id, res["check_out"], res["check_in"]),
    ).fetchone()
    if not new_room:
        conn.close()
        return None

    nights = (datetime.strptime(res["check_out"], "%Y-%m-%d") - datetime.strptime(res["check_in"], "%Y-%m-%d")).days
    total = new_room["price_per_night"] * nights
    cur.execute(
        "UPDATE reservations SET room_id=?, total_price=? WHERE reservation_id=?",
        (new_room["room_id"], total, reservation_id),
    )
    conn.commit()
    conn.close()
    return {"room_number": new_room["room_number"], "total": total, "nights": nights}


def cancel_reservation(db_path, reservation_id):
    """Mark a reservation as cancelled."""
    conn = get_db(db_path)
    conn.execute("UPDATE reservations SET status='cancelled' WHERE reservation_id=?", (reservation_id,))
    conn.commit()
    conn.close()


def find_reservation_by_code(db_path, confirmation_code):
    """Look up a reservation by its confirmation code."""
    conn = get_db(db_path)
    row = conn.execute(
        """
        SELECT res.*, g.full_name, g.email, g.id_number,
               rm.room_type, rm.room_number, rm.price_per_night
        FROM reservations res
        JOIN guests g  ON g.guest_id  = res.guest_id
        JOIN rooms  rm ON rm.room_id  = res.room_id
        WHERE UPPER(res.confirmation_code) = UPPER(?)
        """,
        (confirmation_code.strip(),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_rooms(db_path):
    """Return all rooms with their current booking status for display."""
    conn = get_db(db_path)
    rows = conn.execute(
        "SELECT room_number, room_type, floor, price_per_night, description FROM rooms ORDER BY room_number"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_room_type_summary(db_path):
    """Return one entry per room type with aggregated counts and floor range."""
    conn = get_db(db_path)
    rows = conn.execute(
        """
        SELECT room_type,
               price_per_night,
               description,
               COUNT(*)   AS total_rooms,
               MIN(floor) AS min_floor,
               MAX(floor) AS max_floor
        FROM rooms
        GROUP BY room_type
        ORDER BY price_per_night ASC
        """
    ).fetchall()
    conn.close()

    labels = {
        "classic": "Classic", "superior": "Superior", "deluxe": "Deluxe",
        "suite": "Suite", "penthouse": "Penthouse Suite",
    }
    return [
        {
            "type": r["room_type"],
            "label": labels.get(r["room_type"], r["room_type"].title()),
            "price": r["price_per_night"],
            "description": r["description"],
            "total_rooms": r["total_rooms"],
            "floors": (str(r["min_floor"]) if r["min_floor"] == r["max_floor"]
                       else f"{r['min_floor']}-{r['max_floor']}"),
        }
        for r in rows
    ]
