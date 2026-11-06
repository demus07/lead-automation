"""Sending approved email over plain SMTP (Gmail App Password works, and is free)."""
import os
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid


def configured() -> bool:
    return all(os.getenv(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"))


def send_email(to: str, subject: str, body: str, in_reply_to: str | None = None) -> str:
    """Sends, and returns the Message-ID so a follow-up can continue the thread."""
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg["Message-ID"] = make_msgid(domain=os.getenv("SMTP_USER").split("@")[-1])
    if in_reply_to:
        msg["In-Reply-To"] = msg["References"] = in_reply_to
    msg.set_content(body)
    with smtplib.SMTP(os.getenv("SMTP_HOST"), int(os.getenv("SMTP_PORT", "587")), timeout=30) as smtp:
        smtp.starttls()
        smtp.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD"))
        smtp.send_message(msg)
    return msg["Message-ID"]
