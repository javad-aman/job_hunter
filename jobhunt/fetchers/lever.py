"""Lever ATS poller.

Endpoint: https://api.lever.co/v0/postings/{company}?mode=json

Returns all postings as a JSON array.  Each item includes full description
fields.  No authentication required for public boards.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_BASE = "https://api.lever.co/v0/postings/{company}?mode=json"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str) -> list[Any]:
    resp = await client.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _parse_lever_date(ms_epoch: int | None) -> datetime | None:
    if ms_epoch is None:
        return None
    try:
        return datetime.fromtimestamp(ms_epoch / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _matches_keywords(title: str, keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in keywords)


def _extract_description(job: dict[str, Any]) -> str:
    """Lever stores description in a list of {header, body} dicts."""
    parts = []
    for section in job.get("descriptionBody", {}).get("descriptionBody", []):
        if section.get("header"):
            parts.append(f"## {section['header']}")
        parts.append(section.get("body", ""))
    if not parts:
        # Fall back to plain text description
        parts.append(job.get("description", ""))
    return "\n\n".join(filter(None, parts))


async def fetch_lever(
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
            jobs = await _get(client, url)
        except Exception as exc:
            logger.error("Lever fetch failed for %s (%s): %s", company_name, token, exc)
            return []

    if not isinstance(jobs, list):
        logger.error("Lever: unexpected response shape for %s", company_name)
        return []

    for job in jobs:
        title = job.get("text", "")
        if not _matches_keywords(title, keywords):
            continue

        categories = job.get("categories", {})
        location = categories.get("location", "") or categories.get("allLocations", [""])[0]
        commitment = categories.get("commitment", "").lower()
        remote = "remote" in commitment or "remote" in location.lower() or "remote" in title.lower()

        postings.append(
            Posting(
                title=title,
                company=company_name,
                location=location or "Unknown",
                remote=remote,
                url=job.get("hostedUrl", ""),
                description=_extract_description(job),
                source="lever",
                date_posted=_parse_lever_date(job.get("createdAt")),
            )
        )

    logger.info("Lever %s (%s): %d relevant postings", company_name, token, len(postings))
    return postings
