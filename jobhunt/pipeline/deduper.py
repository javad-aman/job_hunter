"""Two-pass deduplication.

Pass 1 — exact URL dedupe (same job posted on multiple boards).
Pass 2 — title+company key dedupe (same role posted under slightly different URLs).

When a duplicate is found we keep whichever posting has the longer description,
because more content = better LLM scoring.
"""

from __future__ import annotations

from jobhunt.models import Posting


def dedupe(postings: list[Posting]) -> list[Posting]:
    # Pass 1: URL
    seen_urls: dict[str, Posting] = {}
    for p in postings:
        key = p.dedup_key()
        if key not in seen_urls:
            seen_urls[key] = p
        else:
            # Keep whichever has more description content
            if len(p.description) > len(seen_urls[key].description):
                seen_urls[key] = p

    # Pass 2: title+company
    seen_tc: dict[str, Posting] = {}
    for p in seen_urls.values():
        key = p.title_company_key()
        if key not in seen_tc:
            seen_tc[key] = p
        else:
            if len(p.description) > len(seen_tc[key].description):
                seen_tc[key] = p

    result = list(seen_tc.values())
    return result
