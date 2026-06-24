"""Email sender via Resend API (https://resend.com).

Free tier: 3,000 emails/month.  Requires only RESEND_API_KEY + EMAIL_TO in .env.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

from jobhunt.config import cfg

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"


def _md_to_html(md: str) -> str:
    html = md
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.MULTILINE)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.MULTILINE)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', html)
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
    html = html.replace("---", "<hr>")
    html = html.replace("\n\n", "</p><p>").replace("\n", "<br>")
    return f"<html><body><p>{html}</p></body></html>"


def send_email(md_path: Path) -> None:
    """Send digest via Resend. No-ops if RESEND_API_KEY or EMAIL_TO is not set."""
    api_key = cfg.resend_api_key
    to = [addr.strip() for addr in cfg.email_to.split(",") if addr.strip()]

    if not api_key or not to:
        logger.info("Resend not configured — skipping email (set RESEND_API_KEY + EMAIL_TO in .env)")
        return

    subject = "Job Digest " + md_path.stem.replace("digest_", "").replace("_", " ").title()
    body_md = md_path.read_text(encoding="utf-8")
    body_html = _md_to_html(body_md)

    try:
        api_key_str = api_key.decode() if isinstance(api_key, bytes) else str(api_key)
        resp = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key_str}", "Content-Type": "application/json"},
            json={
                "from": "Job Hunt <onboarding@resend.dev>",
                "to": to,
                "subject": subject,
                "html": body_html,
                "text": body_md,
            },
            timeout=15,
        )
        if not resp.is_success:
            logger.error("Resend error %s: %s", resp.status_code, resp.text)
            resp.raise_for_status()
        logger.info("Digest emailed to %s via Resend (id: %s)", to, resp.json().get("id"))
    except httpx.HTTPStatusError:
        pass  # already logged above
    except Exception as exc:
        logger.error("Failed to send email via Resend: %s", exc)
