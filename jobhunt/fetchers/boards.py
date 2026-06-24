"""JobSpy wrapper — scrapes Indeed, Glassdoor, Google Jobs.

JobSpy is synchronous and CPU-bound, so we run it in a thread pool executor
to avoid blocking the asyncio event loop.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

from jobhunt.config import cfg
from jobhunt.models import Posting

logger = logging.getLogger(__name__)

# One shared executor for all board scrapes
_EXECUTOR = ThreadPoolExecutor(max_workers=4)


def _scrape_one(site: str, term: str, location: str = "", is_remote: bool = False) -> list[dict[str, Any]]:
    """Run a single JobSpy scrape synchronously (called in executor thread)."""
    try:
        from jobspy import scrape_jobs  # lazy import — heavy dep
    except ImportError as exc:
        raise RuntimeError("python-jobspy is not installed") from exc

    s = cfg.search
    df = scrape_jobs(
        site_name=[site],
        search_term=term,
        location=location or s.get("location", ""),
        is_remote=is_remote,
        results_wanted=s.get("results_wanted", 100),
        hours_old=s.get("hours_old", 168),
        country_indeed="USA",
    )
    if df is None or df.empty:
        return []
    return df.to_dict("records")


def _row_to_posting(row: dict[str, Any], site: str) -> Posting:
    raw_date = row.get("date_posted")
    if isinstance(raw_date, str):
        try:
            date_posted: datetime | None = datetime.fromisoformat(raw_date)
        except ValueError:
            date_posted = None
    elif isinstance(raw_date, datetime):
        date_posted = raw_date
    else:
        date_posted = None

    is_remote = bool(row.get("is_remote")) or "remote" in str(row.get("location", "")).lower()

    return Posting(
        title=str(row.get("title", "")),
        company=str(row.get("company", "")),
        location=str(row.get("location", "") or "Unknown"),
        remote=is_remote,
        url=str(row.get("job_url", "") or row.get("url", "")),
        description=str(row.get("description", "") or ""),
        source=site,
        date_posted=date_posted,
    )


def _matches_title(title: str, keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in keywords)


async def fetch_boards(location: str = "", is_remote: bool = False) -> list[Posting]:
    """Fetch all configured boards × search terms for a given location."""
    s = cfg.search
    sites: list[str] = s.get("boards", ["indeed", "glassdoor", "google"])
    terms: list[str] = s.get("terms", ["UI UX designer"])
    keywords: list[str] = cfg.ats_title_keywords

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(_EXECUTOR, _scrape_one, site, term, location, is_remote)
        for site in sites
        for term in terms
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    postings: list[Posting] = []
    for (site, term), result in zip(
        [(s, t) for s in sites for t in terms], results
    ):
        if isinstance(result, Exception):
            logger.error("Board scrape failed [%s / %r]: %s", site, term, result)
            continue
        filtered = [row for row in result if _matches_title(str(row.get("title", "")), keywords)]
        for row in filtered:
            postings.append(_row_to_posting(row, site))
        logger.info("Board %s / %r: %d postings (%d dropped by title filter)", site, term, len(filtered), len(result) - len(filtered))

    return postings
