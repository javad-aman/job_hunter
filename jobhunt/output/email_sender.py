"""Optional SMTP email sender.

Sends the Markdown digest as plain text + HTML (Markdown rendered to HTML via
a simple conversion).  Skips silently if SMTP is not configured.
"""

from __future__ import annotations

import logging
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from jobhunt.config import cfg

logger = logging.getLogger(__name__)


def _md_to_html(md: str) -> str:
    """Minimal Markdown → HTML conversion (no external dep)."""
    html = md
    # Headers
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # Inline code
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    # Links
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    # List items
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    # Horizontal rule
    html = html.replace("---", "<hr>")
    # Line breaks → <br> (preserve paragraph structure)
    html = html.replace("\n\n", "</p><p>").replace("\n", "<br>")
    return f"<html><body><p>{html}</p></body></html>"


def send_email(md_path: Path) -> None:
    """Send the digest by email.  No-ops if SMTP is not configured."""
    if not cfg.email_configured():
        logger.info("SMTP not configured — skipping email")
        return

    subject = f"Job Digest {md_path.stem.replace('digest_', '')}"
    body_md = md_path.read_text(encoding="utf-8")
    body_html = _md_to_html(body_md)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.email_from
    msg["To"] = cfg.email_to
    msg.attach(MIMEText(body_md, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg.smtp_user, cfg.smtp_password)
            server.sendmail(cfg.email_from, cfg.email_to, msg.as_string())
        logger.info("Digest emailed to %s", cfg.email_to)
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
