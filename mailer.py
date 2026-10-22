"""
mailer.py — minimal SMTP sender (password-reset emails).

Configure with environment variables:
  SMTP_HOST, SMTP_PORT (default 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM,
  SMTP_TLS=1 (STARTTLS, default) | 0 ;  SMTP_SSL=1 for implicit TLS (port 465).
Without SMTP_HOST nothing is sent and callers fall back (see app.forgot_password).
"""
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("mailer")


def is_configured():
    return bool(os.environ.get("SMTP_HOST"))


def send_mail(to, subject, body):
    """-> True if the server accepted the message, False otherwise (never raises)."""
    if not is_configured():
        return False
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "noreply@localhost"
    msg.set_content(body)
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "465" if os.environ.get("SMTP_SSL") == "1" else "587"))
    try:
        cls = smtplib.SMTP_SSL if os.environ.get("SMTP_SSL") == "1" else smtplib.SMTP
        with cls(host, port, timeout=15) as s:
            if cls is smtplib.SMTP and os.environ.get("SMTP_TLS", "1") != "0":
                s.starttls()
            if os.environ.get("SMTP_USER"):
                s.login(os.environ["SMTP_USER"], os.environ.get("SMTP_PASSWORD", ""))
            s.send_message(msg)
        return True
    except Exception:  # noqa: BLE001 - mail problems must not break the request
        log.exception("Could not send mail to %s", to)
        return False
