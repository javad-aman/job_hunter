"""Workday ATS poller.

Endpoint: POST https://{host}/wday/cxs/{tenant}/{site}/jobs
Body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "designer"}

Workday paginates with offset. We page until we run out of results or hit
max_pages. Filter client-side by title keywords.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_PAGE_SIZE = 20
_MAX_PAGES = 10  # 200 results max per company


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=3, max=15))
async def _post(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post(url, json=body, timeout=20)
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


def _to_posting(job: dict[str, Any], company_name: str, base_url: str) -> Posting:
    title = job.get("title", "")

    locations = job.get("locations", [])
    first_loc = locations[0] if locations else None
    location = first_loc.get("name", "Unknown") if isinstance(first_loc, dict) else str(first_loc or "Unknown")

    is_remote = (
        any("remote" in loc.get("name", "").lower() for loc in locations)
        or "remote" in title.lower()
    )

    external_url = job.get("externalPath", "")
    url = f"{base_url}{external_url}" if external_url.startswith("/") else external_url

    posted_on = job.get("postedOn", "") or job.get("startDate", "")

    return Posting(
        title=title,
        company=company_name,
        location=location,
        remote=is_remote,
        url=url,
        description=job.get("jobDescription", {}).get("descriptor", "") or "",
        source="workday",
        date_posted=_parse_date(posted_on),
    )


async def fetch_workday(
    company_name: str,
    host: str,
    tenant: str,
    site: str,
    keywords: list[str],
    search_text: str = "designer",
) -> list[Posting]:
    base_url = f"https://{host}"
    api_url = f"{base_url}/wday/cxs/{tenant}/{site}/jobs"
    postings: list[Posting] = []

    async with httpx.AsyncClient(
        headers={
            "User-Agent": "jobhunt-bot/1.0 (personal job aggregator)",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
    ) as client:
        offset = 0
        for _ in range(_MAX_PAGES):
            body = {
                "appliedFacets": {},
                "limit": _PAGE_SIZE,
                "offset": offset,
                "searchText": search_text,
            }
            try:
                data = await _post(client, api_url, body)
            except Exception as exc:
                logger.error("Workday fetch failed for %s: %s", company_name, exc)
                break

            jobs = data.get("jobPostings", [])
            if not jobs:
                break

            for job in jobs:
                title = job.get("title", "")
                if not _matches_keywords(title, keywords):
                    continue
                postings.append(_to_posting(job, company_name, base_url))

            total = data.get("total", 0)
            offset += len(jobs)
            if offset >= total:
                break

    logger.info("Workday %s: %d relevant postings", company_name, len(postings))
    return postings
