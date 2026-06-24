"""Ashby ATS poller.

Endpoint: https://api.ashbyhq.com/posting-api/job-board/{company}

Returns a JSON object with a "jobPostings" array.  Each posting has a
"jobCategories" list and a full "descriptionHtml" field.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_BASE = "https://api.ashbyhq.com/posting-api/job-board/{company}"

_HTML_TAG_RE = re.compile(r"<[^>]+>")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    resp = await client.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _strip_html(html: str) -> str:
    return _HTML_TAG_RE.sub(" ", html).strip()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _matches_keywords(title: str, keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in keywords)


async def fetch_ashby(
    company_name: str,
    token: str,
    keywords: list[str],
) -> list[Posting]:
    url = _BASE.format(company=token)
    postings: list[Posting] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "jobhunt-bot/1.0 (personal job aggregator)"}
    ) as client:
        try:
            data = await _get(client, url)
        except Exception as exc:
            logger.error("Ashby fetch failed for %s (%s): %s", company_name, token, exc)
            return []

    for job in data.get("jobPostings", []):
        title = job.get("title", "")
        if not _matches_keywords(title, keywords):
            continue

        location = job.get("locationName", "") or "Unknown"
        is_remote = job.get("isRemote", False) or "remote" in title.lower()

        description_html = job.get("descriptionHtml", "")
        description = _strip_html(description_html) if description_html else ""

        # Ashby job URL: the board page + /jobs/{id}
        job_id = job.get("id", "")
        job_url = job.get("jobUrl", "") or f"https://jobs.ashbyhq.com/{token}/{job_id}"

        postings.append(
            Posting(
                title=title,
                company=company_name,
                location=location,
                remote=is_remote,
                url=job_url,
                description=description,
                source="ashby",
                date_posted=_parse_date(job.get("publishedAt") or job.get("updatedAt")),
            )
        )

    logger.info("Ashby %s (%s): %d relevant postings", company_name, token, len(postings))
    return postings
