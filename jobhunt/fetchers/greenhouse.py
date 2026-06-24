"""Greenhouse ATS poller.

Endpoint: https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true

Returns up to ~250 postings per board (Greenhouse paginates via metadata but
most boards fit in one call).  We filter client-side by title keywords.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_BASE = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    resp = await client.get(url, timeout=20)
    resp.raise_for_status()
    return resp.json()


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


async def fetch_greenhouse(
    company_name: str,
    token: str,
    keywords: list[str],
) -> list[Posting]:
    url = _BASE.format(token=token) + "?content=true"
    postings: list[Posting] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "jobhunt-bot/1.0 (personal job aggregator)"}
    ) as client:
        try:
            data = await _get(client, url)
        except Exception as exc:
            logger.error("Greenhouse fetch failed for %s (%s): %s", company_name, token, exc)
            return []

    for job in data.get("jobs", []):
        title = job.get("title", "")
        if not _matches_keywords(title, keywords):
            continue

        location_parts = [
            loc.get("name", "") for loc in job.get("offices", [])
        ]
        location = ", ".join(filter(None, location_parts)) or "Unknown"

        # content=true includes full description under job["content"]
        description = job.get("content", "") or job.get("absolute_url", "")

        postings.append(
            Posting(
                title=title,
                company=company_name,
                location=location,
                remote="remote" in location.lower() or "remote" in title.lower(),
                url=job.get("absolute_url", ""),
                description=description,
                source="greenhouse",
                date_posted=_parse_date(job.get("updated_at")),
            )
        )

    logger.info("Greenhouse %s (%s): %d relevant postings", company_name, token, len(postings))
    return postings
