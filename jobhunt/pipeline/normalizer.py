"""Light normalization pass applied after all fetchers complete.

Ensures consistent casing, strips whitespace, and enforces non-empty required
fields so the rest of the pipeline can trust the data.
"""

from __future__ import annotations

import re

from jobhunt.models import Posting


_WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize(postings: list[Posting]) -> list[Posting]:
    cleaned: list[Posting] = []
    for p in postings:
        p.title = _clean(p.title)
        p.company = _clean(p.company)
        p.location = _clean(p.location) or "Unknown"
        p.url = p.url.strip()
        # Truncate enormous descriptions early to avoid token waste later
        if len(p.description) > 10_000:
            p.description = p.description[:10_000]

        # Drop postings that have no URL (can't be visited or deduped safely)
        if not p.url:
            continue

        cleaned.append(p)

    return cleaned
