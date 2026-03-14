"""
Email service for Villa Sirene di Positano.

Sends styled HTML confirmation, modification, and cancellation emails.

Transport priority:
    1. Amazon SES via boto3 — uses EC2 IAM role credentials (no passwords)
    2. SMTP relay — configured via .env / environment variables
    3. Graceful no-op with log warning when neither is available

SES env vars (optional overrides):
    SES_REGION  — AWS region for SES (default: eu-central-1)
    SES_SENDER  — verified sender email; auto-detected from SES if unset
SMTP env vars (fallback):
    SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASS
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime


def _load_env():
    """Read key=value pairs from .env if it exists."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

_load_env()

SES_REGION = os.environ.get("SES_REGION", "eu-central-1")
SES_SENDER = os.environ.get("SES_SENDER", "")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

FROM_NAME = "Villa Sirene di Positano"

_ses_client = None
_ses_available = None


def _get_ses_client():
    """Lazily initialise and return a boto3 SES client, or None."""
    global _ses_client, _ses_available
    if _ses_available is not None:
        return _ses_client
    try:
        import boto3
        client = boto3.client("ses", region_name=SES_REGION)
        client.get_send_quota()
        _ses_client = client
        _ses_available = True
        print(f"[Email] SES transport active (region={SES_REGION})")
    except Exception as exc:
        print(f"[Email] SES unavailable: {exc}")
        _ses_client = None
        _ses_available = False
    return _ses_client


def _resolve_ses_sender():
    """Return the SES sender address from config or auto-detect from verified identities."""
    if SES_SENDER:
        return SES_SENDER
    client = _get_ses_client()
    if not client:
        return ""
    try:
        resp = client.list_verified_email_addresses()
        emails = resp.get("VerifiedEmailAddresses", [])
        if emails:
            return emails[0]
    except Exception:
        pass
    return ""


def is_configured():
    """Return True if at least one email transport is usable."""
    if _get_ses_client() and _resolve_ses_sender():
        return True
    return bool(SMTP_USER and SMTP_PASS)


def _send(to_email, subject, html_body):
    """Send an HTML email.  Tries SES first, then SMTP, then logs a skip."""
    client = _get_ses_client()
    sender = _resolve_ses_sender()
    if client and sender:
        return _send_ses(client, sender, to_email, subject, html_body)

    if SMTP_USER and SMTP_PASS:
        return _send_smtp(to_email, subject, html_body)

    print("[Email] No transport configured — skipping send.")
    return False


def _send_ses(client, sender, to_email, subject, html_body):
    """Send via Amazon SES API (boto3)."""
    try:
        client.send_email(
            Source=f"{FROM_NAME} <{sender}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
            },
        )
        print(f"[Email] SES sent '{subject}' to {to_email}")
        return True
    except Exception as exc:
        print(f"[Email] SES send failed ({to_email}): {exc}")
        return False


def _send_smtp(to_email, subject, html_body):
    """Send via SMTP relay (e.g. Gmail with App Password)."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[Email] SMTP sent '{subject}' to {to_email}")
        return True
    except Exception as exc:
        print(f"[Email] SMTP send failed ({to_email}): {exc}")
        return False


def _fmt(iso_date):
    """Format ISO date string to human-readable form."""
    try:
        d = datetime.strptime(iso_date, "%Y-%m-%d")
        return d.strftime("%B %d, %Y")
    except Exception:
        return iso_date


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send_confirmation(to_email, guest_name, code, room_type, room_number,
                      check_in, check_out, nights, total):
    subject = f"Booking Confirmation {code} — Villa Sirene di Positano"
    html = _base_email(
        "Booking Confirmation",
        guest_name,
        "Thank you for choosing Villa Sirene di Positano. "
        "Your reservation has been confirmed. Below are the details of your stay.",
        [
            ("Confirmation", code),
            ("Room", f"{room_type} (Room {room_number})"),
            ("Check-in", _fmt(check_in)),
            ("Check-out", _fmt(check_out)),
            ("Duration", f"{nights} night{'s' if nights != 1 else ''}"),
            ("Total", f"EUR {total:,.0f}"),
        ],
        "We look forward to welcoming you to the Amalfi Coast.",
    )
    return _send(to_email, subject, html)


def send_modification(to_email, guest_name, code, changes):
    """
    Send a modification confirmation.
    `changes` is a list of (label, value) tuples describing what changed.
    """
    subject = f"Booking Updated {code} — Villa Sirene di Positano"
    html = _base_email(
        "Booking Updated",
        guest_name,
        f"Your reservation <strong>{code}</strong> has been updated. "
        "Please find the revised details below.",
        changes,
        "If you have any questions, our concierge is available around the clock.",
    )
    return _send(to_email, subject, html)


def send_cancellation(to_email, guest_name, code):
    subject = f"Booking Cancelled {code} — Villa Sirene di Positano"
    html = _base_email(
        "Booking Cancelled",
        guest_name,
        f"Your reservation <strong>{code}</strong> has been cancelled as requested.",
        [],
        "We hope to have the pleasure of welcoming you in the future.",
    )
    return _send(to_email, subject, html)


# ---------------------------------------------------------------------------
# HTML email template — table-based for maximum client compatibility
# ---------------------------------------------------------------------------

def _detail_rows(details):
    if not details:
        return ""
    rows = ""
    for i in range(0, len(details), 2):
        left = details[i]
        right = details[i + 1] if i + 1 < len(details) else None
        rows += "<tr>"
        rows += (
            f'<td style="padding:10px 14px;border-bottom:1px solid #e8e3d9;">'
            f'<span style="display:block;font-size:10px;text-transform:uppercase;'
            f'letter-spacing:0.06em;color:#999;margin-bottom:2px;">{left[0]}</span>'
            f'<strong style="font-size:14px;color:#1c1c1e;">{left[1]}</strong></td>'
        )
        if right:
            rows += (
                f'<td style="padding:10px 14px;border-bottom:1px solid #e8e3d9;">'
                f'<span style="display:block;font-size:10px;text-transform:uppercase;'
                f'letter-spacing:0.06em;color:#999;margin-bottom:2px;">{right[0]}</span>'
                f'<strong style="font-size:14px;color:#1c1c1e;">{right[1]}</strong></td>'
            )
        else:
            rows += '<td style="padding:10px 14px;border-bottom:1px solid #e8e3d9;"></td>'
        rows += "</tr>"
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#faf8f4;border-radius:6px;border:1px solid #e8e3d9;'
        f'margin:20px 0;">{rows}</table>'
    )


def _base_email(title, guest_name, intro, details, closing):
    details_html = _detail_rows(details)
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f0ebe3;font-family:Georgia,'Times New Roman',serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0ebe3;">
<tr><td align="center" style="padding:32px 12px;">
<table width="580" cellpadding="0" cellspacing="0"
       style="background:#ffffff;border-radius:10px;overflow:hidden;
              box-shadow:0 2px 16px rgba(0,0,0,0.07);">

<!-- Header -->
<tr><td style="background:#0c2340;padding:30px 32px;text-align:center;">
  <div style="width:48px;height:48px;border-radius:50%;border:1.5px solid #c9a84c;
              margin:0 auto 10px;line-height:48px;font-size:16px;font-weight:bold;
              color:#c9a84c;letter-spacing:2px;">VS</div>
  <div style="font-size:22px;color:#ffffff;letter-spacing:0.02em;">Villa Sirene</div>
  <div style="font-size:12px;color:#c9a84c;font-style:italic;letter-spacing:0.04em;
              margin-top:2px;">di Positano</div>
</td></tr>

<!-- Gold line -->
<tr><td style="background:#c9a84c;height:3px;font-size:0;line-height:0;">&nbsp;</td></tr>

<!-- Title -->
<tr><td style="padding:28px 32px 0;text-align:center;">
  <span style="display:inline-block;padding:4px 18px;background:#faf8f4;
               border-radius:20px;font-size:11px;text-transform:uppercase;
               letter-spacing:0.08em;color:#0c2340;font-family:Arial,sans-serif;
               font-weight:bold;">{title}</span>
</td></tr>

<!-- Body -->
<tr><td style="padding:24px 32px 28px;font-size:15px;line-height:1.7;color:#333;">
  <p style="margin:0 0 14px;font-size:17px;color:#0c2340;">
    Dear {guest_name},</p>
  <p style="margin:0 0 6px;">{intro}</p>
  {details_html}
  <p style="margin:16px 0 0;">{closing}</p>
  <p style="margin:24px 0 0;color:#777;font-style:italic;">
    Warm regards,<br>
    <strong>The Concierge Team</strong><br>
    Villa Sirene di Positano
  </p>
</td></tr>

<!-- Footer -->
<tr><td style="background:#faf8f4;padding:16px 32px;border-top:1px solid #e8e3d9;
               text-align:center;font-size:11px;color:#999;
               font-family:Arial,sans-serif;line-height:1.6;">
  Via Cristoforo Colombo 30, 84017 Positano SA, Italy<br>
  info@villasirene.it &middot; +39 089 875 0000
</td></tr>

</table>
</td></tr></table>
</body></html>"""
