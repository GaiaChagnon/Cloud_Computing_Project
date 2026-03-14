#!/usr/bin/env python3
"""
Villa Sirene — Amazon SES Email Setup

Run this ON the EC2 instance after attaching an IAM role with
AmazonSESFullAccess.

Commands:
    python3 setup_ses.py status
        Show SES send quota and list verified email identities.

    python3 setup_ses.py verify EMAIL
        Send a verification request to EMAIL.  Check the inbox and click
        the link.  Once verified, this address can be used as sender/recipient.

    python3 setup_ses.py test SENDER RECIPIENT
        Send a test email from SENDER to RECIPIENT.  Both addresses must
        be verified while the account is in SES sandbox mode.
"""

import sys

REGION = "eu-central-1"


def _client():
    import boto3
    return boto3.client("ses", region_name=REGION)


def cmd_status():
    ses = _client()
    quota = ses.get_send_quota()
    identities = ses.list_verified_email_addresses()
    sandbox = quota["Max24HourSend"] <= 200

    print("--- SES Account Status ---")
    print(f"  Region:            {REGION}")
    print(f"  Mode:              {'SANDBOX' if sandbox else 'PRODUCTION'}")
    print(f"  Max 24h sends:     {quota['Max24HourSend']:.0f}")
    print(f"  Sent last 24h:     {quota['SentLast24Hours']:.0f}")
    print(f"  Max send rate:     {quota['MaxSendRate']:.0f}/sec")
    emails = identities.get("VerifiedEmailAddresses", [])
    print(f"  Verified emails:   {emails if emails else '(none)'}")
    if sandbox:
        print()
        print("  Note: In SANDBOX mode, both sender AND recipient must be verified.")
        print("  Use 'python3 setup_ses.py verify EMAIL' to verify addresses.")


def cmd_verify(email):
    ses = _client()
    ses.verify_email_identity(EmailAddress=email)
    print(f"Verification email sent to {email}")
    print("Open your inbox and click the verification link.")
    print(f"After verifying, you can use {email} as both sender and recipient.")


def cmd_test(sender, recipient):
    ses = _client()
    ses.send_email(
        Source=f"Villa Sirene <{sender}>",
        Destination={"ToAddresses": [recipient]},
        Message={
            "Subject": {"Data": "Test — Villa Sirene Email Service", "Charset": "UTF-8"},
            "Body": {
                "Html": {
                    "Data": (
                        "<h2>Villa Sirene di Positano</h2>"
                        "<p>SES email delivery is configured and working correctly.</p>"
                        "<p style='color:#999;font-size:12px;'>This is an automated test.</p>"
                    ),
                    "Charset": "UTF-8",
                },
            },
        },
    )
    print(f"Test email sent from {sender} to {recipient}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1].lower()

    if cmd == "status":
        cmd_status()
    elif cmd == "verify":
        if len(sys.argv) < 3:
            print("Usage: python3 setup_ses.py verify YOUR@EMAIL.COM")
            return
        cmd_verify(sys.argv[2])
    elif cmd == "test":
        if len(sys.argv) < 4:
            print("Usage: python3 setup_ses.py test SENDER@EMAIL RECIPIENT@EMAIL")
            return
        cmd_test(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)


if __name__ == "__main__":
    main()
