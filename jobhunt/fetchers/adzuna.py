"""Adzuna job aggregator fetcher.

Public REST API — register for a free key at https://developer.adzuna.com
Endpoint: https://api.adzuna.com/v1/api/jobs/us/search/{page}
          ?app_id=...&app_key=...&results_per_page=50&what=...&where=...
          &max_days_old=N&content-type=application/json

Free tier: 1,000 calls / day.  We page through up to `max_pages` to stay
well within that limit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from jobhunt.models import Posting

logger = logging.getLogger(__name__)

_BASE = "https://api.adzuna.com/v1/api/jobs/us/search/{page}"
_RESULTS_PER_PAGE = 50
_MAX_PAGES = 4   # 200 results max per search term — well within free tier


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> dict[str, Any]:
    resp = await client.get(url, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _to_posting(job: dict[str, Any]) -> Posting:
    location_obj = job.get("location", {})
    location = location_obj.get("display_name", "Unknown")

    title = job.get("title", "")
    is_remote = (
        job.get("work_from_home", False)
        or "remote" in title.lower()
        or "remote" in location.lower()
    )

    # Adzuna provides a short description snippet; full text needs a separate call
    description = job.get("description", "")
    company = job.get("company", {}).get("display_name", "Unknown")

    return Posting(
        title=title,
        company=company,
        location=location,
        remote=is_remote,
        url=job.get("redirect_url", ""),
        description=description,
        source="adzuna",
        date_posted=_parse_date(job.get("created")),
    )


def _matches_title(title: str, keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in keywords)


async def fetch_adzuna(
    app_id: str,
    app_key: str,
    terms: list[str],
    location: str,
    hours_old: int = 72,
    results_per_page: int = _RESULTS_PER_PAGE,
    max_pages: int = _MAX_PAGES,
    keywords: list[str] | None = None,
) -> list[Posting]:
    max_days_old = max(1, hours_old // 24)
    all_postings: list[Posting] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "jobhunt-bot/1.0 (personal job aggregator)"}
    ) as client:
        for term in terms:
            page = 1
            fetched = 0
            while page <= max_pages:
                params: dict[str, Any] = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": results_per_page,
                    "what": term,
                    "where": location,
                    "max_days_old": max_days_old,
                    "content-type": "application/json",
                    "sort_by": "date",
                }
                url = _BASE.format(page=page)
                try:
                    data = await _get(client, url, params)
                except Exception as exc:
                    logger.error("Adzuna fetch failed [%r page %d]: %s", term, page, exc)
                    break

                jobs = data.get("results", [])
                if not jobs:
                    break

                before = len(all_postings)
                for job in jobs:
                    p = _to_posting(job)
                    if keywords and not _matches_title(p.title, keywords):
                        continue
                    all_postings.append(p)
                kept = len(all_postings) - before

                fetched += len(jobs)
                total_count = data.get("count", 0)
                logger.debug(
                    "Adzuna %r page %d: got %d (total available: %d)",
                    term, page, len(jobs), total_count,
                )

                if fetched >= total_count or len(jobs) < results_per_page:
                    break
                page += 1

            kept_total = sum(1 for p in all_postings)
            logger.info("Adzuna %r: %d fetched, %d passed title filter", term, fetched, len(all_postings))

    return all_postings
